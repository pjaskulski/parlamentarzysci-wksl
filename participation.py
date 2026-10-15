"""Zastrzeżenia dotyczące funkcji, bez utożsamiania wyboru z obecnością."""
import json
import re


def public_explanation(label, local=''):
    defaults = {
        'Mandat nieuznany': 'Wybór tej osoby na posła nie został uznany za prawidłowy.',
        'Informacja zakwestionowana': 'Przypisanie tej funkcji jest kwestionowane i nie stanowi potwierdzenia udziału w zgromadzeniu.',
        'Mandat niepewny': 'Nie ma pewności, czy był posłem na tym zgromadzeniu.',
        'Udział niepewny': 'Nie ma pewności, czy uczestniczył w tym zgromadzeniu.',
        'Funkcja niepewna': 'Nie ma pewności, czy pełnił tę funkcję podczas zgromadzenia.',
        'Obecność niepotwierdzona': 'Nie potwierdzono jego obecności na obradach.',
        'Identyfikacja osoby niepewna': 'Nie wiadomo, czy wzmianka dotyczy tej osoby, czy innej osoby o podobnym imieniu lub nazwisku.',
        'Rozbieżność źródeł': 'Zachowane przekazy podają rozbieżne informacje o jego udziale w zgromadzeniu.',
    }
    if label == 'Mandat niepewny' and 'poborc' in local.casefold():
        return 'Pełnił funkcję poborcy podatków, ale nie ma pewności, czy był również posłem.'
    return defaults[label]


def participation_notes(row):
    row = dict(row)
    record = row.get('record_json') or {}
    if isinstance(record, str):
        record = json.loads(record)
    context = row.get('context_raw') or record.get('kontekst') or ''
    code = row.get('event_code_raw') or ''
    # Kontekst może wymieniać wiele sejmów. Zastrzeżenie w nawiasie przy innym
    # kodzie nie może zostać przeniesione na aktualne wydarzenie.
    local = code
    if code and (match := re.search(re.escape(code)+r'(?=\s|[,;()]|$)', context)):
        tail = context[match.end():].lstrip()
        if tail.startswith('('):
            depth = 0
            for i, char in enumerate(tail):
                depth += (char == '(') - (char == ')')
                if depth == 0:
                    local += ' '+tail[:i+1]
                    break
    certainty = row.get('certainty')
    attendance = row.get('attendance')
    role = row.get('role')
    notes = []

    def add(label, kind='uncertain'):
        public = record.get('uwagi_publiczne') or {}
        text = public.get(label) if isinstance(public, dict) else None
        explanation = text.strip() if isinstance(text, str) and text.strip() else public_explanation(label, local)
        notes.append(dict(label=label, explanation=explanation, kind=kind))

    correction = record.get('podstawa_korekty')
    if attendance == 'mandat_nieuznany':
        add('Mandat nieuznany', 'disputed')
    elif certainty == 'odrzucone_lub_prostowane':
        add('Informacja zakwestionowana', 'disputed')
    elif certainty == 'niepewne':
        label = 'Mandat niepewny' if role == 'poseł' else 'Udział niepewny' if role in ('senator','uczestnik') else 'Funkcja niepewna'
        add(label)
    if attendance == 'nieustalona' and certainty != 'niepewne':
        add('Obecność niepotwierdzona')

    identity_note = record.get('uwaga_o_niepewności') or row.get('note') or ''
    # Starsze rekordy mogą zawierać w uwadze końcówkę poprzedniego wpisu.
    # Takiego fragmentu nie używamy do identyfikacji bieżącej osoby.
    if not correction and re.search(r'\b1[5-8]\d{2}\b', identity_note):
        identity_note = ''
    identity_text = local+' '+identity_note
    if record.get('niepewność_identyfikacji'):
        add('Identyfikacja osoby niepewna')
    elif certainty == 'niepewne' and re.search(r'\bmoże\s+to\b|\btożsamoś\w*|\bpomyłka co do nazwiska\b', identity_text, re.I):
        add('Identyfikacja osoby niepewna')
    conflict = record.get('sprzeczność_źródłowa')
    if conflict:
        add('Rozbieżność źródeł')
    return notes
