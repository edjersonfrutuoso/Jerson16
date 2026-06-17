import re
import logging

logger = logging.getLogger(__name__)

# Brazilian format: dd/mm/yyyy or dd/mm/yy
BR_DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}/\d{2})')
BR_AMOUNT_RE = re.compile(r'(-?\d{1,3}(?:\.\d{3})*,\d{2})')

# Raiffeisen format: d. m. yyyy
RAIF_DATE_RE = re.compile(r'(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})')
# Raiffeisen amounts use space as thousands separator: -1 000,00
RAIF_AMOUNT_RE = re.compile(r'(-?\d{1,3}(?: \d{3})*,\d{2})')


def parse_amount_br(s: str) -> float:
    return float(s.replace('.', '').replace(',', '.'))


def parse_amount_raif(s: str) -> float:
    return float(s.replace(' ', '').replace(',', '.'))


def parse_date_br(s: str) -> str:
    parts = s.split('/')
    day, month, year = parts[0], parts[1], parts[2]
    if len(year) == 2:
        year = '20' + year
    return f"{year}-{month}-{day}"


def parse_date_raif(m) -> str:
    day = m.group(1).zfill(2)
    month = m.group(2).zfill(2)
    year = m.group(3)
    return f"{year}-{month}-{day}"


def is_raiffeisen(text: str) -> bool:
    return 'Raiffeisen' in text or 'Booked amount' in text


def parse_raiffeisen(pdf) -> list:
    results = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                if not row:
                    continue
                cells = [str(c).strip() if c else '' for c in row]
                if len(cells) < 3:
                    continue

                amount_cell = cells[-1]
                amount_m = RAIF_AMOUNT_RE.search(amount_cell)
                if not amount_m:
                    continue

                date_cell = cells[0]
                date_m = RAIF_DATE_RE.search(date_cell)
                if not date_m:
                    continue

                try:
                    date_str = parse_date_raif(date_m)
                    amount = parse_amount_raif(amount_m.group(1))

                    desc_raw = cells[2] if len(cells) > 2 else ''
                    lines = [l.strip() for l in desc_raw.replace('\\n', '\n').split('\n') if l.strip()]
                    desc = lines[0] if lines else desc_raw.strip()
                    desc = re.sub(r'^(Card payment Apple Pay|Internet Transaction Apple Pay|Card payment)\s*', '', desc).strip()
                    if not desc:
                        desc = desc_raw.strip()

                    if desc and date_str:
                        results.append({'date': date_str, 'description': desc, 'amount': amount})
                except Exception as e:
                    logger.debug(f"Raiffeisen row parse error: {e}")
    return results


def extract_from_line_br(line: str):
    date_m = BR_DATE_RE.search(line)
    amount_m = BR_AMOUNT_RE.search(line)
    if date_m and amount_m:
        try:
            date_str = parse_date_br(date_m.group(1))
            amount = parse_amount_br(amount_m.group(1))
            start = date_m.end()
            end = amount_m.start()
            description = line[start:end].strip(' -|')
            if not description:
                description = line.strip()
            return {'date': date_str, 'description': description, 'amount': amount}
        except Exception as e:
            logger.debug(f"BR line parse error: {line!r}: {e}")
    return None


def parse_pdf(filepath: str) -> list:
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            first_text = pdf.pages[0].extract_text() or ''
            if is_raiffeisen(first_text):
                results = parse_raiffeisen(pdf)
                seen = set()
                unique = []
                for r in results:
                    key = (r['date'], r['description'], r['amount'])
                    if key not in seen:
                        seen.add(key)
                        unique.append(r)
                return unique

            results = []
            for page_num, page in enumerate(pdf.pages):
                try:
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                if row is None:
                                    continue
                                row_text = ' '.join(str(cell) for cell in row if cell)
                                result = extract_from_line_br(row_text)
                                if result:
                                    results.append(result)
                    text = page.extract_text()
                    if text:
                        for line in text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            result = extract_from_line_br(line)
                            if result:
                                key = (result['date'], result['amount'])
                                if not any((r['date'], r['amount']) == key for r in results):
                                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing page {page_num}: {e}")
            return results
    except Exception as e:
        logger.error(f"Failed to parse PDF {filepath}: {e}")
        return []
