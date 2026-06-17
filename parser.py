import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}/\d{2})')
AMOUNT_RE = re.compile(r'(-?\d{1,3}(?:\.\d{3})*,\d{2})')

def parse_amount(s: str) -> float:
    return float(s.replace('.', '').replace(',', '.'))

def parse_date(s: str) -> str:
    parts = s.split('/')
    day, month, year = parts[0], parts[1], parts[2]
    if len(year) == 2:
        year = '20' + year
    return f"{year}-{month}-{day}"

def extract_from_line(line: str):
    date_m = DATE_RE.search(line)
    amount_m = AMOUNT_RE.search(line)
    if date_m and amount_m:
        try:
            date_str = parse_date(date_m.group(1))
            amount = parse_amount(amount_m.group(1))
            start = date_m.end()
            end = amount_m.start()
            description = line[start:end].strip(' -|')
            if not description:
                description = line.strip()
            return {
                'date': date_str,
                'description': description,
                'amount': amount,
                'raw_line': line.strip()
            }
        except Exception as e:
            logger.debug(f"Failed to parse line: {line!r}: {e}")
    return None

def parse_pdf(filepath: str) -> list:
    results = []
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages):
                try:
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                if row is None:
                                    continue
                                row_text = ' '.join(str(cell) for cell in row if cell)
                                result = extract_from_line(row_text)
                                if result:
                                    results.append(result)
                    text = page.extract_text()
                    if text:
                        for line in text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            result = extract_from_line(line)
                            if result:
                                key = (result['date'], result['amount'])
                                if not any((r['date'], r['amount']) == key for r in results):
                                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing page {page_num}: {e}")
    except Exception as e:
        logger.error(f"Failed to parse PDF {filepath}: {e}")
        return []
    return results
