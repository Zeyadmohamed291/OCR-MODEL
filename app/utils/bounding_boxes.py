from typing import List
from app.domain.schemas.core import TextBlock

def sort_text_blocks(blocks: List[TextBlock]) -> List[TextBlock]:
    """
    Groups bounding boxes into lines and sorts them top-to-bottom, right-to-left.
    Strictly adheres to the No Hack Policy: never modifies the OCR text string.
    Only bounding box coordinates are used to mathematically determine reading order.
    """
    if not blocks:
        return []
    
    def get_center_y(block: TextBlock) -> float:
        y_coords = [p[1] for p in block.box.points]
        return sum(y_coords) / 4.0
        
    def get_center_x(block: TextBlock) -> float:
        x_coords = [p[0] for p in block.box.points]
        return sum(x_coords) / 4.0

    # Sort primarily from top to bottom
    blocks.sort(key=get_center_y)
    
    lines = []
    current_line = []
    current_line_y = get_center_y(blocks[0])
    
    for block in blocks:
        block_h = block.box.height
        y = get_center_y(block)
        
        # Threshold: if vertical difference is less than half the block's height, consider it the same line
        if abs(y - current_line_y) < (block_h * 0.5):
            current_line.append(block)
        else:
            lines.append(current_line)
            current_line = [block]
            current_line_y = y
            
    if current_line:
        lines.append(current_line)
        
    sorted_blocks = []
    reading_order_idx = 1
    
    for line_idx, line in enumerate(lines, start=1):
        # Arabic Dominance: sort right to left within the same line
        line.sort(key=get_center_x, reverse=True)
        
        for block in line:
            block.line_number = line_idx
            block.reading_order = reading_order_idx
            sorted_blocks.append(block)
            reading_order_idx += 1
            
    return sorted_blocks
