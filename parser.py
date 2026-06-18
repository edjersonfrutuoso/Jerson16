import re
import logging

logger = logging.getLogger(__name__)

BR_DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}/\d{2})')
BR_AMOUNT_RE = re.compile(r'(-?\d{1,3}(?:\.\d{3})*,\d{2})')

RAIF_DATE_RE = re.compile(r'(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})')
RAIF_DATE_LINE_RE = re.compile(r'^\d{1,2}\.\s*\d{1,2}\.\s*\d{4}')
RAIF_AMOUNT_END_RE = re.compile(r'(-?\d{1,3}(?: \d{3})*,\d{2})\s*$')


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


def parse_date_raif(s: str) -> str:
    m = RAIF_DATE_RE.match(s.strip())
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"


def is_raiffeisen(text: str) -> bool:
    return 'Raiffeisen' in text or 'Booked amount' in text


SKIP_PHRASES = {
    'Transaction Date', 'Booking Date', 'Name of Account',
    'Account Number', 'Account name', 'Transaction history',
    'for period', 'Page ', 'Raiffeisen', 'K0000807',
}

CAT_PREFIX_RE = re.compile(
    r'^(Fee|Interest|Payment|Card payment|Standing order|Incoming payment'
    r'|Outgoing instant payment|Single payment|Loan repayment)\s+'
)
TYPE_PREFIX_RE = re.compile(
    r'^(Card payment Apple Pay|Internet Transaction Apple Pay|Card payment)\s+'
)


def clean_desc(s: str) -> str:
    s = CAT_PREFIX_RE.sub('', s).strip()
    s = TYPE_PREFIX_RE.sub('', s).strip()
    s = re.sub(r'\s+\d{4,10}\s*$', '', s).strip()
    return s


def parse_raiffeisen_text(pdf) -> list:
    results = []
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        lines = text.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or any(p in line for p in SKIP_PHRASES):
                continue
            if not RAIF_DATE_LINE_RE.match(line):
                continue
            amount_m = RAIF_AMOUNT_END_RE.search(line)
            if not amount_m:
                continue

            try:
                date_str = parse_date_raif(line)
                if not date_str:
                    continue
                amount = parse_amount_raif(amount_m.group(1))

                date_end = RAIF_DATE_RE.match(line).end()
                rest = line[date_end:amount_m.start()].strip()
                inline_desc = clean_desc(rest)

                merchant = ''
                if i < len(lines):
                    next_line = lines[i].strip()
                    if (RAIF_DATE_LINE_RE.match(next_line)
                            and not RAIF_AMOUNT_END_RE.search(next_line)
                            and not any(p in next_line for p in SKIP_PHRASES)):
                        next_date_m = RAIF_DATE_RE.match(next_line)
                        merchant_raw = next_line[next_date_m.end():].strip()
                        merchant_raw = re.sub(r'\s+\d{4,10}\s*$', '', merchant_raw).strip()
                        merchant = merchant_raw.split(';')[0].strip()

                desc = merchant if merchant else inline_desc
                if not desc:
                    desc = inline_desc

                if desc:
                    results.append({'date': date_str, 'description': desc, 'amount': amount})
            except Exception as e:
                logger.debug(f"Raiffeisen parse error on line {line!r}: {e}")
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
                results = parse_raiffeisen_text(pdf)
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
