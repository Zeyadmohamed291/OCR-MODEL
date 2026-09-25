import statistics
from typing import List, Tuple, Optional
from app.domain.schemas.core import (
    TextBlock, BoundingBox, LayoutInfo, LayoutBlock, LayoutLine,
    LayoutSection, LayoutTable, LayoutCell
)
from app.services.language.language_detector import LanguageDetector
from app.services.layout.bidi_formatter import normalize_logical_text

class LayoutAnalyzer:
    """
    Performs layout analysis, block hierarchy grouping, section identification,
    and table structure discovery from sorted OCR text blocks.
    Strictly preserves logical Unicode order without string reversals.
    """

    @classmethod
    def analyze(
        cls,
        blocks: List[TextBlock],
        image_width: int = 1000,
        image_height: int = 1000
    ) -> Tuple[LayoutInfo, List[LayoutSection], List[LayoutTable]]:
        if not blocks:
            return LayoutInfo(pages=1, blocks=[], lines=[]), [], []

        # 1. Group Blocks into LayoutLines
        lines_dict = {}
        for block in blocks:
            l_num = block.line_number
            if l_num not in lines_dict:
                lines_dict[l_num] = []
            lines_dict[l_num].append(block)

        layout_lines: List[LayoutLine] = []
        for l_num in sorted(lines_dict.keys()):
            line_blocks = lines_dict[l_num]
            line_text = " ".join(b.text for b in line_blocks)
            raw_text = " ".join(b.raw_text or b.text for b in line_blocks)
            normalized_text = normalize_logical_text(line_text)
            
            line_lang, _, _ = LanguageDetector.detect(line_text)
            line_dir = LanguageDetector.detect_direction(line_text)
            avg_conf = sum(b.confidence for b in line_blocks) / len(line_blocks) if line_blocks else 0.0

            # Compute union bounding box
            all_x = [p[0] for b in line_blocks for p in b.box.points]
            all_y = [p[1] for b in line_blocks for p in b.box.points]
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)
            w, h = max_x - min_x, max_y - min_y

            norm_pts = [
                (min_x / max(image_width, 1), min_y / max(image_height, 1)),
                (max_x / max(image_width, 1), min_y / max(image_height, 1)),
                (max_x / max(image_width, 1), max_y / max(image_height, 1)),
                (min_x / max(image_width, 1), max_y / max(image_height, 1)),
            ]
            bbox_poly = [
                [float(min_x), float(min_y)],
                [float(max_x), float(min_y)],
                [float(max_x), float(max_y)],
                [float(min_x), float(max_y)]
            ]
            bbox = BoundingBox(
                points=[(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)],
                normalized_points=norm_pts,
                width=w,
                height=h,
                area=w * h
            )

            layout_lines.append(LayoutLine(
                line_number=l_num,
                text=line_text,
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=line_lang,
                direction=line_dir,
                confidence=round(avg_conf, 3),
                box=bbox,
                bbox=bbox_poly,
                reading_order=l_num
            ))

        # 2. Group Lines into LayoutBlocks (Paragraphs)
        heights = [l.box.height for l in layout_lines if l.box]
        median_h = statistics.median(heights) if heights else 20.0

        layout_blocks: List[LayoutBlock] = []
        current_block_lines: List[LayoutLine] = []
        block_id = 1

        def _make_block(b_id: int, b_lines: List[LayoutLine]) -> LayoutBlock:
            b_text = "\n".join(l.text for l in b_lines)
            b_raw = "\n".join(l.raw_text or l.text for l in b_lines)
            b_norm = normalize_logical_text(b_text)
            b_lang, _, _ = LanguageDetector.detect(b_text)
            b_dir = LanguageDetector.detect_direction(b_text)
            avg_b_conf = sum(l.confidence for l in b_lines) / len(b_lines)
            
            # Block union bounding box
            b_min_x = min(l.box.points[0][0] for l in b_lines if l.box) if any(l.box for l in b_lines) else 0.0
            b_min_y = min(l.box.points[0][1] for l in b_lines if l.box) if any(l.box for l in b_lines) else 0.0
            b_max_x = max(l.box.points[2][0] for l in b_lines if l.box) if any(l.box for l in b_lines) else 0.0
            b_max_y = max(l.box.points[2][1] for l in b_lines if l.box) if any(l.box for l in b_lines) else 0.0
            
            b_bbox_poly = [
                [float(b_min_x), float(b_min_y)],
                [float(b_max_x), float(b_min_y)],
                [float(b_max_x), float(b_max_y)],
                [float(b_min_x), float(b_max_y)]
            ]
            b_bbox = BoundingBox(
                points=[(b_min_x, b_min_y), (b_max_x, b_min_y), (b_max_x, b_max_y), (b_min_x, b_max_y)],
                normalized_points=[
                    (b_min_x / max(image_width, 1), b_min_y / max(image_height, 1)),
                    (b_max_x / max(image_width, 1), b_min_y / max(image_height, 1)),
                    (b_max_x / max(image_width, 1), b_max_y / max(image_height, 1)),
                    (b_min_x / max(image_width, 1), b_max_y / max(image_height, 1)),
                ],
                width=b_max_x - b_min_x,
                height=b_max_y - b_min_y,
                area=(b_max_x - b_min_x) * (b_max_y - b_min_y)
            )

            return LayoutBlock(
                block_id=b_id,
                type="paragraph",
                text=b_text,
                raw_text=b_raw,
                normalized_text=b_norm,
                language=b_lang,
                direction=b_dir,
                confidence=round(avg_b_conf, 3),
                box=b_bbox,
                bbox=b_bbox_poly,
                reading_order=b_id,
                lines=b_lines
            )

        def is_header_line(l: LayoutLine) -> bool:
            if not l.box:
                return False
            if l.box.height > (median_h * 1.30) and len(l.text.split()) <= 8:
                return True
            txt_lower = l.text.strip().lower()
            words = txt_lower.split()
            sec_kws = [
                "البند", "الفصل", "المادة", "ديباجة", "الشروط", "الموضوع",
                "section", "clause", "article", "summary", "experience", "education",
                "skills", "projects", "certifications", "invoice", "receipt"
            ]
            if words and any(txt_lower.startswith(kw) or words[0] == kw for kw in sec_kws):
                if len(words) <= 10:
                    return True
            return False

        for i, line in enumerate(layout_lines):
            if not current_block_lines:
                current_block_lines.append(line)
                continue

            prev_line = current_block_lines[-1]
            gap = 0.0
            if line.box and prev_line.box:
                prev_bottom = max(p[1] for p in prev_line.box.points)
                curr_top = min(p[1] for p in line.box.points)
                gap = max(0.0, curr_top - prev_bottom)

            # Header lines start a new block, and lines immediately following a header start a new block
            if is_header_line(line) or is_header_line(prev_line) or gap > (median_h * 1.7):
                layout_blocks.append(_make_block(block_id, current_block_lines))
                block_id += 1
                current_block_lines = [line]
            else:
                current_block_lines.append(line)

        if current_block_lines:
            layout_blocks.append(_make_block(block_id, current_block_lines))

        # 3. Detect Document Title, Header, and Footer
        doc_title: Optional[str] = None
        doc_header: Optional[str] = None
        doc_footer: Optional[str] = None
        has_signatures: bool = False

        if layout_lines:
            # Check signatures across all lines
            for l in layout_lines:
                l_lower = l.text.lower()
                if any(kw in l_lower for kw in ["توقيع", "التوقيع", "signature", "signatures", "signed by", "معتمد", "ختم"]):
                    has_signatures = True
                    break

            # Candidate title: largest font height line in top 30% of document
            top_lines = [l for l in layout_lines if l.box and (l.box.points[0][1] <= max(image_height * 0.30, 200))]
            if top_lines:
                best_title_line = max(top_lines, key=lambda l: (l.box.height if l.box else 0, -len(l.text)))
                if len(best_title_line.text.split()) <= 10 and not any(kw in best_title_line.text.lower() for kw in ["page", "صفحة", "http", "date", "تاريخ"]):
                    doc_title = best_title_line.text.strip()

            # Running header: line in top 8% of page
            header_candidates = [l for l in layout_lines if l.box and (l.box.points[2][1] <= max(image_height * 0.08, 60))]
            if header_candidates and header_candidates[0].text.strip() != doc_title:
                doc_header = header_candidates[0].text.strip()

            # Running footer: line in bottom 8% of page or page numbering
            footer_candidates = [l for l in layout_lines if l.box and (l.box.points[0][1] >= min(image_height * 0.90, image_height - 60) or "page" in l.text.lower() or "صفحة" in l.text)]
            if footer_candidates:
                doc_footer = footer_candidates[-1].text.strip()

        # 4. Detect Multi-Column Layouts
        num_columns = 1
        if blocks and len(blocks) >= 4:
            left_blocks = sum(1 for b in blocks if (b.box.points[2][0] <= (image_width * 0.48)))
            right_blocks = sum(1 for b in blocks if (b.box.points[0][0] >= (image_width * 0.52)))
            if left_blocks >= 2 and right_blocks >= 2:
                num_columns = 2

        # 5. Detect Sections (Headings) and Group Body Content
        sections: List[LayoutSection] = []
        for block in layout_blocks:
            first_line = block.lines[0] if block.lines else None
            if first_line and is_header_line(first_line):
                block.type = "header"

        # Associate content blocks with preceding header
        for i, block in enumerate(layout_blocks):
            if block.type == "header":
                first_line = block.lines[0] if block.lines else None
                header_title = first_line.text.strip() if first_line else block.text.strip()
                
                # If this header is the document title itself, do not duplicate it as a sub-section
                if doc_title and header_title == doc_title:
                    continue

                content_parts: List[str] = []
                if len(block.lines) > 1:
                    content_parts.append("\n".join(l.text for l in block.lines[1:]))

                all_sec_x = [p[0] for l in block.lines for p in (l.box.points if l.box else [])]
                all_sec_y = [p[1] for l in block.lines for p in (l.box.points if l.box else [])]

                for j in range(i + 1, len(layout_blocks)):
                    next_b = layout_blocks[j]
                    if next_b.type == "header":
                        break
                    content_parts.append(next_b.text)
                    if next_b.lines:
                        for l in next_b.lines:
                            if l.box:
                                all_sec_x.extend(p[0] for p in l.box.points)
                                all_sec_y.extend(p[1] for p in l.box.points)

                body_content = "\n".join(content_parts).strip()
                
                if all_sec_x and all_sec_y:
                    s_min_x, s_max_x = min(all_sec_x), max(all_sec_x)
                    s_min_y, s_max_y = min(all_sec_y), max(all_sec_y)
                    sec_bbox = [
                        [float(s_min_x), float(s_min_y)],
                        [float(s_max_x), float(s_min_y)],
                        [float(s_max_x), float(s_max_y)],
                        [float(s_min_x), float(s_max_y)]
                    ]
                else:
                    sec_bbox = block.bbox

                sections.append(LayoutSection(
                    title=header_title,
                    level=1,
                    content=body_content,
                    confidence=0.95,
                    bbox=sec_bbox,
                    text=f"{header_title}\n{body_content}".strip(),
                    box=first_line.box if first_line else block.box
                ))

        # 6. Table Detection Heuristic
        tables = cls._detect_tables(layout_lines)

        layout_info = LayoutInfo(
            pages=1,
            title=doc_title,
            header=doc_header,
            footer=doc_footer,
            columns=num_columns,
            has_signatures=has_signatures,
            blocks=layout_blocks,
            lines=layout_lines,
            tables=tables
        )

        return layout_info, sections, tables

    @classmethod
    def _detect_tables(cls, lines: List[LayoutLine]) -> List[LayoutTable]:
        """
        Discovers table rows based on multiple spaced tokens and column alignments.
        Populates structured cells, headers, and rows with cell-level direction.
        """
        tables: List[LayoutTable] = []
        potential_table_rows: List[List[str]] = []

        for line in lines:
            parts = [p.strip() for p in line.text.split("  ") if p.strip()]
            if len(parts) >= 3:
                potential_table_rows.append(parts)
            elif len(parts) == 2 and any(char.isdigit() for char in line.text):
                potential_table_rows.append(parts)

        # If at least 2 consecutive multi-column lines exist, form a table
        if len(potential_table_rows) >= 2:
            max_cols = max(len(r) for r in potential_table_rows)
            headers_str = potential_table_rows[0]
            
            # Determine overall table direction from content
            table_sample = " ".join(" ".join(r) for r in potential_table_rows)
            table_lang, _, _ = LanguageDetector.detect(table_sample)
            table_dir = "rtl" if table_lang == "ar" else "ltr"

            cells: List[LayoutCell] = []
            structured_headers: List[LayoutCell] = []
            structured_rows: List[List[LayoutCell]] = []

            for r_idx, row in enumerate(potential_table_rows):
                row_cells: List[LayoutCell] = []
                for c_idx, val in enumerate(row):
                    cell_lang, _, _ = LanguageDetector.detect(val)
                    cell_dir = LanguageDetector.detect_direction(val)
                    cell = LayoutCell(
                        row=r_idx,
                        col=c_idx,
                        text=val,
                        raw_text=val,
                        normalized_text=normalize_logical_text(val),
                        language=cell_lang,
                        direction=cell_dir,
                        confidence=0.95
                    )
                    cells.append(cell)
                    row_cells.append(cell)
                    if r_idx == 0:
                        structured_headers.append(cell)
                if r_idx > 0:
                    structured_rows.append(row_cells)

            tables.append(LayoutTable(
                table_id=1,
                rows=len(potential_table_rows),
                cols=max_cols,
                direction=table_dir,
                headers=headers_str,
                cells=cells,
                raw_data=potential_table_rows,
                structured_headers=structured_headers,
                structured_rows=structured_rows
            ))

        return tables
