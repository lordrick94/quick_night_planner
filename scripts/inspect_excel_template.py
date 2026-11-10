"""Dump the full structure of an Excel night-plan template.

Created by JXP and Claude

Used to document the night-plan workbook format (docs/excel_night_plan_format.md)
from a real past plan. The dump includes cell *values*, which may be real
targets, so write it somewhere git-ignored (default: next to the template).

For every sheet it lists: dimensions, freeze panes, column widths, non-default
row heights, merged ranges, data validations, conditional formats, print
setup, and then every non-empty cell with its value or formula, number format,
font, fill, alignment and border. It ends with a summary of formula
*patterns*: each formula with row numbers rewritten relative to its own row
(``{r}``, ``{r-1}``, ...) so repeated per-row formulas collapse into one line.

Usage
-----
    python scripts/inspect_excel_template.py pvt_templates/Lick_2026A-4_Night_plan.xlsx

Inputs
------
xlsx : path to the workbook.
--out : Markdown dump path (default: <xlsx dir>/_inspect/<stem>_structure.md).

Outputs
-------
The Markdown dump; prints its path.
"""

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

CELL_REF = re.compile(r'(\$?)([A-Z]{1,3})(\$?)(\d+)')


def relative_formula(formula, row):
    """
    Rewrite row numbers in a formula relative to the formula's own row.

    Inputs
    ------
    formula : str, e.g. '=B7+C6'
    row : int, the row the formula lives in

    Outputs
    -------
    str, e.g. '=B{r}+C{r-1}' (absolute $-rows are kept as numbers)
    """
    def sub(m):
        cabs, col, rabs, num = m.groups()
        if rabs:
            return f'{cabs}{col}{rabs}{num}'
        off = int(num) - row
        tag = 'r' if off == 0 else f'r{off:+d}'
        return f'{cabs}{col}{{{tag}}}'
    return CELL_REF.sub(sub, formula)


def describe_style(cell):
    """
    Short text description of a cell's style.

    Inputs
    ------
    cell : openpyxl cell

    Outputs
    -------
    str (empty when everything is default)
    """
    bits = []
    f = cell.font
    if f is not None:
        if f.b:
            bits.append('bold')
        if f.i:
            bits.append('italic')
        if f.sz and float(f.sz) != 11:
            bits.append(f'size {f.sz:g}')
        if f.color is not None and f.color.type == 'rgb' and f.color.rgb not in (None, 'FF000000'):
            bits.append(f'font {f.color.rgb}')
        if f.name and f.name != 'Calibri':
            bits.append(f'face {f.name}')
    fill = cell.fill
    if fill is not None and fill.fill_type:
        c = fill.fgColor
        col = c.rgb if c is not None and c.type == 'rgb' else (f'theme{c.theme}' if c is not None else '?')
        bits.append(f'fill {fill.fill_type} {col}')
    a = cell.alignment
    if a is not None:
        if a.horizontal:
            bits.append(f'h-{a.horizontal}')
        if a.vertical:
            bits.append(f'v-{a.vertical}')
        if a.wrap_text:
            bits.append('wrap')
    b = cell.border
    if b is not None:
        sides = [s for s in ('left', 'right', 'top', 'bottom')
                 if getattr(b, s) is not None and getattr(b, s).style]
        if sides:
            bits.append('border ' + '/'.join(f'{s}:{getattr(b, s).style}' for s in sides))
    if cell.number_format and cell.number_format != 'General':
        bits.append(f'fmt "{cell.number_format}"')
    return ', '.join(bits)


def dump_sheet(ws, lines, patterns):
    """
    Append one sheet's structure to lines; collect formula patterns.

    Inputs
    ------
    ws : openpyxl worksheet
    lines : list of str, output (appended to)
    patterns : dict sheet -> Counter of (column, relative formula)

    Outputs
    -------
    none
    """
    lines += [f'## Sheet `{ws.title}`', '',
              f'- dimensions: {ws.dimensions} (max row {ws.max_row}, max col {ws.max_column})',
              f'- freeze panes: {ws.freeze_panes}',
              f'- sheet state: {ws.sheet_state}; tab colour: '
              f'{ws.sheet_properties.tabColor.rgb if ws.sheet_properties.tabColor else None}',
              f'- print: orientation {ws.page_setup.orientation}, fitToWidth '
              f'{ws.page_setup.fitToWidth}, fitToHeight {ws.page_setup.fitToHeight}, '
              f'print area {ws.print_area}, print titles rows {ws.print_title_rows}',
              f'- gridlines shown: {ws.sheet_view.showGridLines}; zoom {ws.sheet_view.zoomScale}']
    widths = {k: round(v.width, 2) for k, v in ws.column_dimensions.items() if v.width}
    lines.append(f'- column widths: {widths}')
    heights = {k: v.height for k, v in ws.row_dimensions.items() if v.height}
    lines.append(f'- non-default row heights: {heights}')
    lines.append(f'- merged ranges: {sorted(str(m) for m in ws.merged_cells.ranges)}')
    dvs = ws.data_validations.dataValidation if ws.data_validations else []
    for dv in dvs:
        lines.append(f'- data validation {dv.sqref}: type {dv.type}, formula1 {dv.formula1}, '
                     f'allow blank {dv.allow_blank}')
    for rng, rules in ws.conditional_formatting._cf_rules.items():
        for rule in rules:
            lines.append(f'- conditional format {rng.sqref}: type {rule.type}, '
                         f'operator {rule.operator}, formula {rule.formula}')
    lines += ['', '| cell | value / formula | style |', '|---|---|---|']
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None and not describe_style(cell):
                continue
            v = cell.value
            if isinstance(v, str) and v.startswith('='):
                patterns[ws.title][(cell.column_letter, relative_formula(v, cell.row))] += 1
            shown = repr(v).replace('|', '\\|').replace('\n', '\\n')
            lines.append(f'| {cell.coordinate} | `{shown}` | {describe_style(cell)} |')
    lines.append('')


def main():
    """
    Parse arguments and write the dump.

    Inputs
    ------
    command-line arguments (see module docstring).

    Outputs
    -------
    none; writes the Markdown dump.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('xlsx')
    parser.add_argument('--out', default=None)
    args = parser.parse_args()

    path = Path(args.xlsx)
    out = (Path(args.out) if args.out
           else path.parent / '_inspect' / f'{path.stem}_structure.md')
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.load_workbook(path)  # formulas, not cached values
    lines = [f'# Structure of `{path.name}`', '',
             'Created by JXP and Claude -- generated by '
             '`scripts/inspect_excel_template.py`. Contains cell values: keep private.',
             '', f'Sheets, in order: {wb.sheetnames}', '',
             f'Defined names: {list(wb.defined_names.keys()) if hasattr(wb.defined_names, "keys") else wb.defined_names}',
             '']
    patterns = defaultdict(Counter)
    for ws in wb.worksheets:
        dump_sheet(ws, lines, patterns)
    lines += ['# Formula patterns ({r} = the formula\'s own row)', '']
    for sheet, counter in patterns.items():
        lines += [f'## `{sheet}`', '', '| column | pattern | count |', '|---|---|---|']
        for (col, pat), n in sorted(counter.items()):
            lines.append(f'| {col} | `{pat}` | {n} |')
        lines.append('')
    out.write_text('\n'.join(lines) + '\n')
    print(out)


if __name__ == '__main__':
    main()
