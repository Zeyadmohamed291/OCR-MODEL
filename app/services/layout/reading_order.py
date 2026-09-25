import re
from typing import List, Tuple
from app.domain.schemas.core import TextBlock, BoundingBox
from app.services.language.language_detector import LanguageDetector
from app.services.layout.bidi_formatter import normalize_logical_text

ARABIC_CHAR_PATTERN = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
LATIN_CHAR_PATTERN = re.compile(r'[a-zA-Z]')
DIGIT_CHAR_PATTERN = re.compile(r'[0-9]')

def get_block_bounds(block: TextBlock) -> Tuple[float, float, float, float]:
    """Returns (min_x, min_y, max_x, max_y) for a block."""
    x_coords = [p[0] for p in block.box.points]
    y_coords = [p[1] for p in block.box.points]
    return min(x_coords), min(y_coords), max(x_coords), max(y_coords)

def get_block_center(block: TextBlock) -> Tuple[float, float]:
    """Returns (center_x, center_y) for a block."""
    min_x, min_y, max_x, max_y = get_block_bounds(block)
    return (min_x + max_x) / 2.0, (min_y + max_y) / 2.0

def get_block_direction(block: TextBlock) -> str:
    """Returns 'rtl' or 'ltr' for a single block."""
    text = block.text or ""
    ar_count = len(ARABIC_CHAR_PATTERN.findall(text))
    lat_count = len(LATIN_CHAR_PATTERN.findall(text))
    
    if ar_count > lat_count:
        return "rtl"
    return "ltr"

def get_line_direction(line: List[TextBlock]) -> str:
    """
    Determines whether a line's primary reading direction is RTL or LTR.
    Looks at strong directional characters across the entire line.
    """
    ar_total = sum(len(ARABIC_CHAR_PATTERN.findall(b.text)) for b in line)
    lat_total = sum(len(LATIN_CHAR_PATTERN.findall(b.text)) for b in line)
    
    if ar_total > lat_total:
        return "rtl"
    elif lat_total > ar_total:
        return "ltr"
    
    # If no letters (pure numbers/symbols), reading order is LTR
    if ar_total == 0 and lat_total == 0:
        return "ltr"
        
    # Tie-breaker: check horizontal edge block scripts
    if line:
        rightmost = max(line, key=lambda b: get_block_center(b)[0])
        if len(ARABIC_CHAR_PATTERN.findall(rightmost.text)) > 0:
            return "rtl"
    return "ltr"

def sort_line_bidi_runs(line: List[TextBlock], line_direction: str) -> List[TextBlock]:
    """
    Sorts blocks in a line using Bidi directional runs without any string reversal.
    - Contiguous RTL blocks form RTL runs.
    - Contiguous LTR blocks (English, numbers, codes, dates) form LTR runs.
    - Across runs:
        * If line is RTL, runs on the right come first.
        * If line is LTR, runs on the left come first.
    - Within each run:
        * RTL run: blocks ordered Right-to-Left (x descending).
        * LTR run: blocks ordered Left-to-Right (x ascending).
    """
    if len(line) <= 1:
        return line

    # 1. Sort all blocks left-to-right along the X-axis
    sorted_ltr = sorted(line, key=lambda b: get_block_bounds(b)[0])

    # 2. Partition into contiguous directional runs
    runs: List[List[TextBlock]] = []
    current_run: List[TextBlock] = []
    current_run_dir = get_block_direction(sorted_ltr[0])

    for block in sorted_ltr:
        block_dir = get_block_direction(block)
        if block_dir == current_run_dir:
            current_run.append(block)
        else:
            if current_run:
                runs.append(current_run)
            current_run = [block]
            current_run_dir = block_dir

    if current_run:
        runs.append(current_run)

    # 3. Order the runs across the line according to primary line direction
    if line_direction == "rtl":
        # In RTL line, runs further to the RIGHT (larger X center) come first
        runs.sort(
            key=lambda r: sum(get_block_center(b)[0] for b in r) / len(r),
            reverse=True
        )
    else:
        # In LTR line, runs further to the LEFT (smaller X center) come first
        runs.sort(
            key=lambda r: sum(get_block_center(b)[0] for b in r) / len(r),
            reverse=False
        )

    # 4. Order blocks within each run
    ordered_blocks: List[TextBlock] = []
    for run in runs:
        run_dir = get_block_direction(run[0])
        if run_dir == "rtl":
            # RTL run: sort Right-to-Left (x descending)
            run.sort(key=lambda b: get_block_center(b)[0], reverse=True)
        else:
            # LTR run: sort Left-to-Right (x ascending)
            run.sort(key=lambda b: get_block_center(b)[0], reverse=False)
        ordered_blocks.extend(run)

    return ordered_blocks

def organize_reading_order(blocks: List[TextBlock], image_width: int = 0) -> List[TextBlock]:
    """
    Geometry-aware hierarchical reading order reconstruction.
    1. Clusters blocks into lines using Y-center proximity relative to median block height.
       This is robust against tall/multi-line blocks that break overlap-based grouping.
    2. Sorts lines top-to-bottom.
    3. Within each line, determines direction (RTL or LTR).
    4. Applies Bidi run sorting to preserve LTR runs (numbers, codes) inside RTL lines.
    5. Sets raw_text, normalized_text, language, direction, line_number, reading_order.
    """
    if not blocks:
        return []

    # Pre-compute bounding boxes once for efficiency
    bounds_cache = {id(b): get_block_bounds(b) for b in blocks}

    # Sort top-to-bottom by the block's top edge
    sorted_by_y = sorted(blocks, key=lambda b: bounds_cache[id(b)][1])

    # ---------------------------------------------------------------
    # Compute median block height — used as a global reference for
    # deciding whether two blocks share the same visual line.
    # Using median (not mean) prevents outlier tall blocks from skewing
    # the threshold.
    # ---------------------------------------------------------------
    raw_heights = [
        max(bounds_cache[id(b)][3] - bounds_cache[id(b)][1], 5.0)
        for b in sorted_by_y
    ]
    raw_heights_sorted = sorted(raw_heights)
    median_h = raw_heights_sorted[len(raw_heights_sorted) // 2]

    # Two blocks belong to the same line if their Y-centers are within
    # this fraction of the median line height.
    LINE_CENTER_TOLERANCE = median_h * 0.65

    # ---------------------------------------------------------------
    # Cluster blocks into lines by Y-center proximity
    # ---------------------------------------------------------------
    lines: List[List[TextBlock]] = []
    current_line: List[TextBlock] = []

    first_b = bounds_cache[id(sorted_by_y[0])]
    current_line_center_y = (first_b[1] + first_b[3]) / 2.0

    for block in sorted_by_y:
        bx0, by0, bx1, by1 = bounds_cache[id(block)]
        block_center_y = (by0 + by1) / 2.0

        if abs(block_center_y - current_line_center_y) <= LINE_CENTER_TOLERANCE:
            current_line.append(block)
            # Recalculate line center as the mean of all member centers
            centers = [
                (bounds_cache[id(b)][1] + bounds_cache[id(b)][3]) / 2.0
                for b in current_line
            ]
            current_line_center_y = sum(centers) / len(centers)
        else:
            if current_line:
                lines.append(current_line)
            current_line = [block]
            current_line_center_y = block_center_y

    if current_line:
        lines.append(current_line)

    # ---------------------------------------------------------------
    # Sort lines top-to-bottom by their average Y-center
    # ---------------------------------------------------------------
    lines.sort(
        key=lambda ln: sum(
            (bounds_cache[id(b)][1] + bounds_cache[id(b)][3]) / 2.0
            for b in ln
        ) / max(len(ln), 1)
    )

    # ---------------------------------------------------------------
    # Within each line apply Bidi run sorting; assign metadata
    # ---------------------------------------------------------------
    final_blocks: List[TextBlock] = []
    reading_order_idx = 1

    for line_idx, line in enumerate(lines, start=1):
        line_direction = get_line_direction(line)
        ordered_line = sort_line_bidi_runs(line, line_direction)

        for block in ordered_line:
            if not block.raw_text:
                block.raw_text = block.text
            block.normalized_text = normalize_logical_text(block.text)
            block.script = LanguageDetector.detect_script(block.text)
            block.language, _, _ = LanguageDetector.detect(block.text)
            block.direction = LanguageDetector.detect_direction(block.text)
            block.line_number = line_idx
            block.line = line_idx
            block.reading_order = reading_order_idx
            final_blocks.append(block)
            reading_order_idx += 1

    return final_blocks
