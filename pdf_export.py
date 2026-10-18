"""Eksport kart osób i wydarzeń do PDF, bez zapisywania plików na serwerze."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


FONTS = Path(__file__).resolve().parent/'fonts'
for name,file in [('CatalogSans','DejaVuSans.ttf'),('CatalogBold','DejaVuSans-Bold.ttf'),('CatalogSerif','DejaVuSerif.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONTS/file)))
pdfmetrics.registerFontFamily('CatalogSans',normal='CatalogSans',bold='CatalogBold',italic='CatalogSans',boldItalic='CatalogBold')

INK = colors.HexColor('#292723')
MUTED = colors.HexColor('#6c6a63')
ACCENT = colors.HexColor('#946126')
LINE = colors.HexColor('#e2e1da')


def build_person_pdf(context, *, app_title, format_source, certainty):
    """Zwróć strumień PDF z tym samym zestawem danych co karta WWW."""
    person,record = context['person'],context['record']
    stream = BytesIO()
    doc = SimpleDocTemplate(stream,pagesize=A4,rightMargin=20*mm,leftMargin=20*mm,
        topMargin=22*mm,bottomMargin=24*mm,title=person['name'],
        author='Pracownia Historii Cyfrowej IHPAN',subject=app_title)
    body = ParagraphStyle('Body',fontName='CatalogSans',fontSize=9,leading=14,
        textColor=INK,spaceAfter=7,alignment=TA_LEFT,splitLongWords=True)
    styles = {
        'body':body,
        'small':ParagraphStyle('Small',parent=body,fontSize=8,leading=12,textColor=MUTED),
        'title':ParagraphStyle('Title',parent=body,fontName='CatalogSerif',fontSize=23,leading=30,spaceAfter=12),
        'heading':ParagraphStyle('Heading',parent=body,fontName='CatalogSerif',fontSize=14,leading=19,
            spaceBefore=15,spaceAfter=9,keepWithNext=True),
        'biogram':ParagraphStyle('Biogram',parent=body,fontName='CatalogSerif',fontSize=10,leading=16),
        'label':ParagraphStyle('Label',parent=body,fontName='CatalogBold',fontSize=8,leading=12,textColor=MUTED),
    }
    story = []

    def paragraph(text, style='body'):
        # Źródła są zwykłym tekstem, nie poleceniami formatowania ReportLab.
        text = str(text or '').replace('\u00a0',' ').replace('\u2011','-')
        return Paragraph(escape(text).replace('\n','<br/>'),styles[style])

    def heading(text):
        story.append(paragraph(text,'heading'))

    def table(headers,rows,widths):
        values = [[paragraph(h,'label') for h in headers]]
        values.extend([[paragraph(cell) for cell in row] for row in rows])
        item = LongTable(values,colWidths=[doc.width*w for w in widths],repeatRows=1,hAlign='LEFT')
        item.setStyle(TableStyle([
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
            ('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),6),
            ('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.6,LINE),
            ('LINEBELOW',(0,1),(-1,-1),.35,LINE),
        ]))
        story.append(item)

    def certainty_label(value):
        return certainty.get(value,value or '') if value!='stwierdzone_w_źródle' else ''

    def items(values, bibliography=False):
        for item in values:
            if isinstance(item,dict):
                text = item.get('zapis',item.get('cel',''))
                if bibliography:
                    text = format_source(text)
                story.append(paragraph(text))
                note = item.get('uwaga')
                if note == 'Fragment listy kariery; możliwa elipsa urzędu lub kontynuacja datowania.':
                    note = None
                level = item.get('pewność')
                label = '' if level=='niepewne' and str(text).lower().startswith('prawdopodobnie ') else certainty_label(level)
                notes = [label,note]
                if any(notes):
                    story.append(paragraph(' · '.join(str(n) for n in notes if n),'small'))
            else:
                story.append(paragraph(format_source(item) if bibliography else item))

    story.append(paragraph(app_title,'small'))
    story.append(Spacer(1,5*mm))
    story.append(paragraph(person['name'],'title'))
    dates = []
    for key,label in [('birth_date_raw','Data urodzenia'),('baptism_date_raw','Data chrztu'),('death_date_raw','Data śmierci')]:
        if person.get(key):
            dates.append(label+': '+person[key])
    story.append(paragraph(' · '.join(dates) if dates else 'Daty życia niepodane w źródle','small'))

    names = []
    for key,label in [('given_names','Imiona'),('surname','Nazwisko'),('patronymic','Otczestwo'),
        ('surname_variants','Warianty nazwiska'),('given_name_variants','Warianty imienia'),
        ('patronymic_variants','Warianty otczestwa'),('other_name_variants','Pozostałe człony nazwy')]:
        value = person.get(key)
        if value:
            names.append((label,'; '.join(value) if isinstance(value,list) else value))
    if names:
        heading('Imiona / Nazwiska / Warianty')
        table(['',''],names,[.3,.7])

    heading('Tekst biogramu')
    story.append(paragraph(person['biogram'],'biogram'))

    if context['offices']:
        heading('Urzędy')
        rows = []
        for office in context['offices']:
            name = office['name']
            if office['office_type']:
                name += '\nRodzaj: '+office['office_type']
            if office['certainty']=='odrzucone_lub_prostowane' and not office['name'].lower().startswith('niedoszły '):
                name += '\n'+certainty_label(office['certainty'])
            date = office['dating_raw'] or 'Niepodane'
            rows.append((name,date))
        table(['Urząd','Datowanie'],rows,[.73,.27])

    if context['titles']:
        heading('Inne stopnie, godności i określenia rodzinne')
        for title in context['titles']:
            story.append(paragraph('Określenie rodzinne' if title['kind']=='family_designation' else 'Stopień lub godność','small'))
            story.append(paragraph(title['description_raw']))

    if context['roles']:
        heading('Funkcje parlamentarne')
        story.append(paragraph('/I, /II, /III oznacza kolejność w roku, /k — konwokację. Znak ? wskazuje niepewność.','small'))
        rows = []
        for role in context['roles']:
            if role['event_id']:
                event = role['event_name']+' ('+role['event_code_raw']+')\n'+(role['event_place'] or 'Miejsce niepodane')+'\n'+role['event_date_raw']
                if role['occurrence_status'] in ('not_held','cancelled'):
                    event += '\nObrady nie odbyły się'
            else:
                event = role['event_code_raw']+'\nWydarzenie nieustalone'
            representation = '; '.join(role.get('representations',[])) or '-'
            role_label=role['role'].capitalize()
            if role['attendance']=='mandat_nieuznany':role_label+=' — mandat nieuznany'
            rows.append((event,role_label,representation))
        table(['Sejm lub zjazd','Rola','Posłował z'],rows,[.52,.14,.34])

    for key,values in context['sections']:
        if values:
            heading(key.replace('_',' ').capitalize())
            items(values,bibliography=key=='źródła')

    def page_decoration(canvas, document):
        canvas.saveState()
        width,height = A4
        canvas.setStrokeColor(LINE)
        canvas.line(20*mm,18*mm,width-20*mm,18*mm)
        canvas.setFillColor(MUTED)
        canvas.setFont('CatalogSans',7)
        canvas.drawString(20*mm,13*mm,'Pracownia Historii Cyfrowej IHPAN, 2026')
        canvas.drawRightString(width-20*mm,13*mm,f'Strona {document.page}')
        if document.page>1:
            canvas.setFont('CatalogSans',7)
            canvas.drawString(20*mm,height-14*mm,'Baza Parlamentarzystów Wielkiego Księstwa Litewskiego 1566–1793')
        canvas.restoreState()

    doc.build(story,onFirstPage=page_decoration,onLaterPages=page_decoration)
    stream.seek(0)
    return stream


def build_event_pdf(context, *, app_title, role_names, translate=lambda text: text):
    """Eksport karty wydarzenia, z tymi samymi grupami osób co w widoku WWW."""
    from reportlab.lib.pagesizes import landscape
    from reportlab.platypus import CondPageBreak

    event = context['event']
    stream = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(stream, pagesize=page_size, rightMargin=18*mm,
        leftMargin=18*mm, topMargin=18*mm, bottomMargin=20*mm,
        title=translate(event['name']), author='Pracownia Historii Cyfrowej IHPAN',
        subject=app_title)
    body = ParagraphStyle('EventBody', fontName='CatalogSans', fontSize=9,
        leading=13, textColor=INK, spaceAfter=6)
    small = ParagraphStyle('EventSmall', parent=body, fontSize=8,
        leading=12, textColor=MUTED)
    title = ParagraphStyle('EventTitle', parent=body, fontName='CatalogSerif',
        fontSize=22, leading=28, spaceAfter=10)
    heading = ParagraphStyle('EventHeading', parent=body, fontName='CatalogSerif',
        fontSize=14, leading=19, spaceBefore=14, spaceAfter=8, keepWithNext=True)
    group_heading = ParagraphStyle('EventGroupHeading', parent=heading, keepWithNext=False)
    label = ParagraphStyle('EventLabel', parent=body, fontName='CatalogBold',
        fontSize=8, leading=12, textColor=MUTED)
    story, footnotes, note_numbers = [], [], {}

    def paragraph(text, style=body):
        text = str(text or '').replace('\u00a0', ' ').replace('\u2011', '-')
        return Paragraph(escape(text).replace('\n', '<br/>'), style)

    def references(notes):
        numbers = []
        for note in notes:
            key = (note['label'], note['explanation'])
            if key not in note_numbers:
                note_numbers[key] = len(footnotes)+1
                footnotes.append(key)
            number = note_numbers[key]
            if number not in numbers:
                numbers.append(number)
        return ' '+''.join(f'[{n}]' for n in numbers) if numbers else ''

    story.append(paragraph(app_title, small))
    codes = ' · '.join(event['codes'])
    if codes:
        story.append(paragraph(codes, small))
    story.append(paragraph(translate(event['name']), title))
    story.append(paragraph(' · '.join(filter(None, [event.get('place'), event.get('date_raw')]))))
    story.append(paragraph(translate('Osoby:')+' '+str(context['people_count']), small))
    if event['occurrence_status'] in ('not_held', 'cancelled'):
        story.append(paragraph(translate('Obrady nie odbyły się.')))
    if len(event['sessions']) > 1:
        story.append(paragraph(translate('Części obrad'), heading))
        for session in event['sessions']:
            text = ' · '.join(filter(None, [session.get('place') or event.get('place'), session.get('date_raw')]))
            if session.get('continuation'):
                text += ' · '+translate('Kontynuacja po limicie')
            story.append(paragraph(text))

    if not context['groups']:
        story.append(paragraph(translate('Brak powiązanych osób.')))
    for role, people in context['groups'].items():
        group_title = paragraph(translate(role_names.get(role, role.capitalize()))+
                                ' ('+str(len(people))+')', group_heading)
        headers = ['Osoba', 'Lata życia']
        if role == 'poseł':
            headers.append('Posłował z')
        headers.append('Urzędy')
        values = [[paragraph(translate(h), label) for h in headers]]
        for person in people:
            life = person['life_years']
            if translate('Lata życia') != 'Lata życia':
                # Skróty interfejsu, bez zmieniania historycznego datowania.
                life = life.replace('ur.', 'b.').replace('zm.', 'd.')
            cells = [person['name']+references(person['participation_notes']), life]
            if role == 'poseł':
                cells.append('; '.join(person['representations']) or '-')
            cells.append(', '.join(person['offices']) or '-')
            values.append([paragraph(cell) for cell in cells])
        widths = [.27, .13, .17, .43] if role == 'poseł' else [.29, .14, .57]
        table = LongTable(values, colWidths=[doc.width*w for w in widths],
            repeatRows=1, hAlign='LEFT', splitByRow=1, splitInRow=1)
        table_style = TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LINEBELOW', (0,0), (-1,0), .6, LINE),
            ('LINEBELOW', (0,1), (-1,-1), .35, LINE),
        ])
        table.setStyle(table_style)
        # Zwiąż nagłówek z pierwszym wierszem, zamiast przenosić całą długą
        # tabelę na następną stronę przez keepWithNext.
        first_rows = LongTable(values[:2], colWidths=[doc.width*w for w in widths])
        first_rows.setStyle(table_style)
        first_height = first_rows.wrap(doc.width, doc.height)[1]
        title_height = group_title.wrap(doc.width, doc.height)[1]
        story.extend([CondPageBreak(first_height+title_height+
                                   group_title.getSpaceBefore()+group_title.getSpaceAfter()),
                      group_title, table])
    if footnotes:
        story.append(paragraph(translate('Zastrzeżenia dotyczące udziału'), heading))
        for number, (note_label, explanation) in enumerate(footnotes, 1):
            story.append(paragraph(f'[{number}] '+translate(note_label)+': '+translate(explanation), small))

    def decoration(canvas, document):
        width, height = page_size
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(18*mm, 15*mm, width-18*mm, 15*mm)
        canvas.setFillColor(MUTED)
        canvas.setFont('CatalogSans', 7)
        canvas.drawString(18*mm, 10*mm, 'Pracownia Historii Cyfrowej IHPAN, 2026')
        canvas.drawRightString(width-18*mm, 10*mm, translate('Strona')+' '+str(document.page))
        if document.page > 1:
            canvas.drawString(18*mm, height-11*mm, app_title)
        canvas.restoreState()

    doc.build(story, onFirstPage=decoration, onLaterPages=decoration)
    stream.seek(0)
    return stream
