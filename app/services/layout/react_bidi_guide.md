# Bidi-Safe React Frontend Guide

This guide explains how frontend applications (React, Next.js, Vue, vanilla JS) should consume and visually display the OCR engine's output.

## Core Rules

1. **Logical Order is Preserved**:
   - The backend delivers all text strings in **logical Unicode order**.
   - **DO NOT** reverse strings using `.split('').reverse().join('')` or CSS `transform: scaleX(-1)`.
   - The browser's native **Unicode Bidirectional Algorithm (UBA)** performs glyph rendering and RTL shaping automatically.

2. **Direction Attributes**:
   - For pure Arabic strings (`direction: "rtl"`): render with `dir="rtl"`.
   - For pure English / Numbers / Codes / Dates / Emails / URLs (`direction: "ltr"`): render with `dir="ltr"`.
   - For mixed Arabic-English strings (`direction: "auto"`): render with `dir="auto"`.

3. **Use `<bdi>` (Bidirectional Isolation)**:
   - When displaying an English value or number inside an Arabic sentence or vice versa, wrap the dynamic value in `<bdi>`:
   ```jsx
   <div dir="rtl">
     رقم الفاتورة: <bdi dir="ltr">{field.value}</bdi>
   </div>
   ```
   - This ensures punctuation and trailing characters (e.g. `INV-1023:`, `$100.50`, `+2010...`) do not jump to the opposite side of the screen.

4. **CSS Logical Properties**:
   - Use CSS logical properties instead of physical left/right rules:
   ```css
   /* Correct */
   margin-inline-start: 1rem;
   padding-inline-end: 0.5rem;
   border-inline-start: 3px solid #3b82f6;
   text-align: start;

   /* Avoid */
   margin-left: 1rem;
   padding-right: 0.5rem;
   border-left: 3px solid #3b82f6;
   text-align: left;
   ```

5. **Tables**:
   - Use the `direction` attribute on the `<table>` element:
   ```jsx
   <table dir={table.direction || "ltr"}>
     <thead>
       <tr>
         {table.structured_headers.map((h, i) => (
           <th key={i} dir={h.direction || "auto"}><bdi>{h.text}</bdi></th>
         ))}
       </tr>
     </thead>
     <tbody>
       {table.structured_rows.map((row, rIdx) => (
         <tr key={rIdx}>
           {row.map((cell, cIdx) => (
             <td key={cIdx} dir={cell.direction || "auto"}><bdi>{cell.text}</bdi></td>
           ))}
         </tr>
       ))}
     </tbody>
   </table>
   ```

## Example React Component

```tsx
import React from 'react';

interface StructuredField {
  label?: string;
  value: any;
  language: string;
  direction: 'rtl' | 'ltr' | 'auto';
  confidence: number;
}

export const OCRFieldCard: React.FC<{ field: StructuredField }> = ({ field }) => {
  return (
    <div 
      className="p-4 rounded-lg border bg-slate-900 border-slate-800"
      style={{ borderInlineStart: '4px solid #3b82f6' }}
    >
      <div className="flex justify-between items-center text-xs text-slate-400 mb-1">
        <span dir="auto">{field.label || 'Field'}</span>
        <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold bg-slate-800">
          {field.direction}
        </span>
      </div>
      <div 
        className="text-base font-semibold text-white" 
        dir={field.direction}
      >
        <bdi>{String(field.value)}</bdi>
      </div>
    </div>
  );
};
```
