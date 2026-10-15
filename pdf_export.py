"""Eksport danych karty osoby do PDF, bez zapisywania plików na serwerze."""
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
                notes = [certainty_label(item.get('pewność')),note]
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
            if certainty_label(office['certainty']):
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
        table(['Sejm lub zjazd','Rola','Reprezentacja'],rows,[.52,.14,.34])

    for key,values in context['sections']:
        if values:
            heading(key.replace('_',' ').capitalize())
            items(values,bibliography=key=='źródła')
    if record.get('odsyłacze'):
        heading('Odsyłacze w biogramie')
        items(record['odsyłacze'])

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
            canvas.drawString(20*mm,height-14*mm,'Baza Parlamentarzystów Wielkiego Księstwa Litewskiego 1566-1793')
        canvas.restoreState()

    doc.build(story,onFirstPage=page_decoration,onLaterPages=page_decoration)
    stream.seek(0)
    return stream
