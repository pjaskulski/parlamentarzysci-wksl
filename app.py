#!/usr/bin/env python3
"""Prototyp katalogu biogramów Flask, dostęp wyłącznie do odczytu."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import urlencode, parse_qs

from flask import Flask, abort, g, render_template, request, send_file, url_for, redirect
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

if __package__:
    from .pdf_export import build_person_pdf, build_event_pdf
    from .docx_export import build_person_docx, build_event_docx
    from .career import build_career
    from .xlsx_export import build_event_xlsx, build_people_xlsx, build_events_xlsx
    from .participation import display_participation_notes as participation_notes, distinct_explanations
    from .summaries import ranked_participations
    from .i18n import translate, language, counted
else:
    from pdf_export import build_person_pdf, build_event_pdf
    from docx_export import build_person_docx, build_event_docx
    from career import build_career
    from xlsx_export import build_event_xlsx, build_people_xlsx, build_events_xlsx
    from participation import display_participation_notes as participation_notes, distinct_explanations
    from summaries import ranked_participations
    from i18n import translate, language, counted

ROOT = Path(__file__).resolve().parent
TITLE = 'Baza Parlamentarzystów Wielkiego Księstwa Litewskiego 1566–1793'
ALPHABET = 'aąbcćdeęfghijklłmnńoópqrsśtuvwxyzźż'
ROLE_NAMES = {'poseł':'Posłowie','senator':'Senatorowie','marszałek':'Marszałkowie','uczestnik':'Pozostali uczestnicy'}
CERTAINTY = {'stwierdzone_w_źródle':'Stwierdzone w źródle','niepewne':'Niepewne',
             'odrzucone_lub_prostowane':'Odrzucone lub prostowane','uzupełnienie_redakcyjne':'Uzupełnienie redakcyjne'}


def polish_key(text):
    text = unicodedata.normalize('NFC', text or '').casefold()
    return tuple(ALPHABET.index(c)+1 if c in ALPHABET else 100+ord(c) for c in text)


def fold(text):
    text = text.translate(str.maketrans({'ł':'l','Ł':'L'}))
    return ''.join(c for c in unicodedata.normalize('NFD',text) if not unicodedata.combining(c))


def territory_parts(text):
    """Nazwy składowe bez rozstrzygania charakteru wspólnego przypisania."""
    return [part.strip() for part in re.split(r',|\s+i\s+', text or '') if part.strip()]


def territory_matches(text, query):
    needle = fold(query).casefold().strip()
    return any(fold(part).casefold().startswith(needle) for part in territory_parts(text))


def fts_query(query, mode):
    if mode == 'fts':
        return query
    if mode == 'phrase':
        return '"'+fold(query).replace('"','""')+'"'
    terms = []
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', query):
        term = fold(phrase or word)
        prefix = bool(word and term.endswith('*'))
        if prefix:
            term = term[:-1]
        if term:
            terms.append('"'+term.replace('"','""')+'"'+('*' if prefix else ''))
    return ' AND '.join(terms)


def safe_snippet(value):
    # Wyłącznie nasze dwa znaczniki stają się HTML; tekst źródłowy jest escaped.
    return Markup(str(escape(value or '')).replace('\ue000','<mark>').replace('\ue001','</mark>'))


def people_label(rows):
    count = len({row['person_id'] for row in rows})
    noun = 'osoba' if count==1 else 'osoby' if count%10 in (2,3,4) and count%100 not in (12,13,14) else 'osób'
    return f'{count} {noun}'


def life_years(person):
    def year(raw):
        if not raw:
            return None
        match = re.search(r'\[?\b[12]\d{3}(?:\s*[/–—-]\s*\d{1,4})?\??\]?',raw)
        if not match:
            return raw
        qualifier = re.search(r'\b(?:a/l\.|a\.|ok\.|około|przed|po)\s*',raw[:match.start()])
        return (qualifier[0].strip()+' ' if qualifier else '')+match[0]
    birth,death = year(person['birth_date_raw']),year(person['death_date_raw'])
    if birth and death:
        return birth+' – '+death
    return 'ur. '+birth if birth else 'zm. '+death if death else '-'


def format_source(value):
    """Rozwiń opis PSB, zachowując uwagi i pozostałą bibliografię."""
    pattern = r'\bPSB\b(?:\s+(?:t\.\s*)?(?P<volume>[IVXLCDM]+(?:/\d+)?)\b)?(?:\s*,?\s*(?:s\.\s*)?(?P<pages>\d+(?:\s*[-–—]\s*\d+)?))?'

    def expand(match):
        result = 'Polski Słownik Biograficzny'
        if match['volume']:
            result += ', t. '+match['volume']
        if match['pages']:
            result += ', s. '+re.sub(r'\s*[-–—]\s*','–',match['pages'])
        return result

    return re.sub(pattern,expand,value or '')


def create_app(config=None):
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.update(DATABASE=os.environ.get('BIOGRAMS_DATABASE',str(ROOT/'instance/biograms.sqlite')),
                      MAX_CONTENT_LENGTH=1024*1024)
    if config:
        app.config.update(config)
    path = Path(app.config['DATABASE']).resolve()
    if not path.is_file():
        raise ValueError(f'Brak bazy biogramów: {path}. Wskaż plik opcją --database lub zmienną BIOGRAMS_DATABASE.')
    app.config['DATABASE'] = path

    @app.before_request
    def choose_language():
        requested = request.args.get('lang')
        saved = request.cookies.get('parliament-language', 'pl')
        g.language = requested if requested in ('pl', 'en') else saved if saved in ('pl', 'en') else 'pl'

    @app.url_defaults
    def language_links(endpoint, values):
        if endpoint != 'static' and language() == 'en':
            values.setdefault('lang', 'en')

    def language_url(selected):
        allowed = {'q', 'mode', 'role', 'office', 'letter', 'sort', 'page',
                   'year_from', 'year_to', 'code', 'type', 'view', 'territory', 'catalogue', 'include_uncertain'}
        values = {key:request.args.getlist(key) for key in allowed if key in request.args}
        values.update(request.view_args or {})
        values['lang'] = selected
        return url_for(request.endpoint or 'index', **values)

    def get_db():
        if 'db' not in g:
            g.db = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA query_only=ON')
            g.db.execute('PRAGMA foreign_keys=ON')
            g.db.create_collation('POLISH',lambda a,b:(polish_key(a)>polish_key(b))-(polish_key(a)<polish_key(b)))
            g.db.create_function('territory_matches',2,territory_matches)
            g.db.create_function('search_fold',1,lambda text:fold(text or '').casefold())
        return g.db

    @app.teardown_appcontext
    def close_db(error=None):
        db = g.pop('db',None)
        if db is not None:
            db.close()

    with app.app_context():
        db = get_db()
        if db.execute('PRAGMA application_id').fetchone()[0]!=1112100687:
            raise ValueError('To nie jest samodzielna baza biogramów; wskaż biograms.sqlite.')
        if db.execute('PRAGMA user_version').fetchone()[0]<3:
            raise ValueError('Baza wymaga kalendarium: uruchom src/integrate_events.py --apply.')
        app.config['CATALOG_COUNT'] = db.execute('SELECT count(*) FROM persons').fetchone()[0]

    app.jinja_env.filters['json_load'] = lambda value:json.loads(value) if value else []
    app.jinja_env.filters['snippet'] = safe_snippet
    app.jinja_env.globals['_'] = translate
    app.jinja_env.filters['translate'] = translate
    app.jinja_env.filters['certainty'] = lambda value:translate(CERTAINTY.get(value,value or ''))
    app.jinja_env.filters['pretty_number'] = lambda value:f'{value:,}'.replace(',',' ')
    app.jinja_env.filters['format_source'] = format_source
    app.jinja_env.filters['people_label'] = lambda rows:counted(len({r['person_id'] for r in rows}), 'osoba', 'osoby', 'osób')
    app.jinja_env.filters['biogram_count'] = lambda count:counted(count, 'biogram', 'biogramów', 'biogramów')
    app.jinja_env.filters['role_count'] = lambda count:counted(count, 'funkcja parlamentarna', 'funkcje parlamentarne', 'funkcji parlamentarnych')
    app.jinja_env.filters['life_text'] = lambda text:re.sub(r'\bur\.', 'b.', text).replace('zm.', 'd.') if language() == 'en' else text

    @app.context_processor
    def common():
        return {'app_title':translate(TITLE),'catalog_count':app.config['CATALOG_COUNT'],
                'role_names':{k:translate(v) for k,v in ROLE_NAMES.items()},
                'language':language(), 'language_url':language_url}

    @app.after_request
    def headers(response):
        if request.endpoint != 'static':
            response.headers['Content-Language'] = language()
            response.vary.add('Cookie')
            if (request.args.get('lang') in ('pl', 'en')
                    and language() != request.cookies.get('parliament-language', 'pl')):
                response.set_cookie('parliament-language', language(), max_age=365*24*60*60,
                    path=request.script_root or '/', httponly=True,
                    secure=request.is_secure, samesite='Lax')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.route('/')
    def index(export=False, navigation_args=None):
        args = request.args if navigation_args is None else navigation_args
        db = get_db()
        q = args.get('q','').strip()
        mode = args.get('mode','words')
        role = args.get('role','')
        office = args.get('office','').strip()
        territory = args.get('territory','').strip() if role == 'poseł' else ''
        has_representations = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='role_representations'").fetchone())
        territories = sorted({part for row in db.execute('SELECT DISTINCT territory_name FROM role_representations') for part in territory_parts(row[0])}, key=polish_key) if has_representations else []
        letter = args.get('letter','').casefold()
        sort = args.get('sort','relevance' if q else 'name')
        page_raw = args.get('page','1')
        start_raw,end_raw = args.get('year_from','').strip(),args.get('year_to','').strip()
        filters = dict(q=q,mode=mode,role=role,office=office,territory=territory,letter=letter,sort=sort,year_from=start_raw,year_to=end_raw)
        error = None
        if len(q)>300 or len(office)>100 or len(territory)>100:
            error = 'Zapytanie jest zbyt długie. Skróć tekst wyszukiwania.'
        elif mode not in ('words','phrase','fts') or role not in ('',*ROLE_NAMES) or sort not in ('name','relevance') or (letter and letter not in ALPHABET):
            error = 'Niepoprawny filtr wyszukiwania.'
        year_from = year_to = None
        try:
            page = int(page_raw)
            if page<1:
                raise ValueError()
            year_from = int(start_raw) if start_raw else None
            year_to = int(end_raw) if end_raw else None
            if any(y is not None and not 1400<=y<=1900 for y in (year_from,year_to)) or (year_from and year_to and year_from>year_to):
                raise ValueError()
        except ValueError:
            page = 1
            error = 'Podaj poprawną stronę i zakres lat (1400–1900), od wcześniejszego do późniejszego roku.'
        conditions,params = [],[]
        join = ''
        snippet = "substr(p.biogram,1,230) AS excerpt"
        score = '0 AS score'
        query = fts_query(q,mode) if not error and q else ''
        if q and not error and not query:
            error = 'Podaj słowo lub frazę do wyszukania.'
        if query:
            join = 'JOIN persons_fts ON persons_fts.rowid=p.person_id'
            conditions.append('persons_fts MATCH ?')
            params.append(query)
            snippet = "snippet(persons_fts,2,char(57344),char(57345),' … ',32) AS excerpt"
            score = 'bm25(persons_fts,8,5,2,0.3) AS score'
        if letter:
            conditions.append('substr(lower(p.surname),1,1)=? OR substr(p.surname,1,1)=?')
            params.extend([letter,letter.upper()])
            conditions[-1] = '('+conditions[-1]+')'
        if office:
            literal = fold(office).casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            conditions.append("EXISTS(SELECT 1 FROM person_offices o WHERE o.person_id=p.person_id AND (search_fold(o.name) LIKE ? ESCAPE '\\' OR search_fold(o.office_type) LIKE ? ESCAPE '\\'))")
            params.extend(['%'+literal+'%']*2)
        if role or year_from or year_to or territory:
            event_conditions = ['er.person_id=p.person_id']
            if role:
                event_conditions.append('er.role=?');params.append(role)
            if territory:
                if has_representations:
                    event_conditions.append('EXISTS(SELECT 1 FROM role_representations rr WHERE rr.role_id=er.role_id AND territory_matches(rr.territory_name,?))')
                    params.append(territory)
                else:
                    event_conditions.append('0')
            if year_from:
                event_conditions.append('COALESCE(e.year_end,er.year_end,er.year_start)>=?');params.append(year_from)
            if year_to:
                event_conditions.append('COALESCE(e.year_start,er.year_start)<=?');params.append(year_to)
            conditions.append('EXISTS(SELECT 1 FROM person_event_roles er LEFT JOIN events e ON e.event_id=er.event_id WHERE '+' AND '.join(event_conditions)+')')
        query_active=bool(q or office or role or letter or start_raw or end_raw)
        if export and not query_active:
            abort(400)
        where = 'WHERE '+' AND '.join(conditions) if conditions else ''
        total,pages,people = 0,1,[]
        if not error:
            try:
                total = db.execute(f'SELECT count(*) FROM persons p {join} {where}',params).fetchone()[0]
                pages = max(1,math.ceil(total/24));page=min(page,pages)
                order = 'score,' if sort=='relevance' and query else ''
                order += "COALESCE(p.surname,p.name) COLLATE POLISH,p.given_names COLLATE POLISH,p.person_id"
                limit = '' if export or navigation_args is not None else ' LIMIT 24 OFFSET ?'
                people = db.execute(f'''SELECT p.person_id,p.name,p.birth_date_raw,p.death_date_raw,
                    {snippet},{score},(SELECT count(*) FROM person_event_roles er WHERE er.person_id=p.person_id) AS role_count
                    FROM persons p {join} {where} ORDER BY {order}'''+limit,
                    params if export or navigation_args is not None else [*params,(page-1)*24]).fetchall()
            except sqlite3.OperationalError:
                if not query:
                    raise
                error = 'Niepoprawna składnia wyszukiwania. Sprawdź cudzysłowy i operatory lub wybierz „Wszystkie słowa”.'
        if navigation_args is not None:
            return dict(ids=[p['person_id'] for p in people] if not error else [],
                        filters=filters, active=query_active, error=error)
        if export and not error:
            offices, codes = {}, {}
            ids = {p['person_id'] for p in people}
            # Jedno odczytanie list, bez osobnego zapytania dla każdej osoby.
            for office_row in db.execute('''SELECT person_id,name FROM person_offices
                ORDER BY COALESCE(dating_year_min,dating_year_max) IS NULL,
                    COALESCE(dating_year_min,dating_year_max),position'''):
                pid=office_row['person_id'];name=office_row['name'].strip()
                if pid in ids and name and name not in offices.setdefault(pid,[]):offices[pid].append(name)
            for role_row in db.execute('''SELECT person_id,event_code_raw FROM person_event_roles
                ORDER BY year_start,year_end,position'''):
                pid=role_row['person_id'];code=role_row['event_code_raw']
                if pid in ids and code and code not in codes.setdefault(pid,[]):codes[pid].append(code)
            rows=[dict(p,life_years=life_years(p),offices=offices.get(p['person_id'],[]),
                       event_codes=codes.get(p['person_id'],[])) for p in people]
            stream=build_people_xlsx(rows,translate=translate)
            response=send_file(stream,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               as_attachment=True,download_name='parlamentarzysci-wyniki.xlsx')
            response.headers['Cache-Control']='no-store'
            return response
        export_url=url_for('people_xlsx',**{k:v for k,v in filters.items() if v})
        def page_url(number):
            return url_for('index',**{k:v for k,v in filters.items() if v},page=number)
        catalogue = urlencode({**{k:v for k,v in filters.items() if v}, 'page':page})
        def person_url(person_id):
            return url_for('person',person_id=person_id,catalogue=catalogue)
        return render_template('index.html',filters=filters,people=people,total=total,error=error,
            page=page,pages=pages,page_url=page_url,page_numbers=range(max(1,page-2),min(pages,page+2)+1),
            person_url=person_url,territories=territories,alphabet=ALPHABET.upper(),export_url=export_url,query_active=query_active),400 if error else 200

    @app.route('/persons/export.xlsx')
    def people_xlsx():
        return index(export=True)

    def representation_labels(rows):
        ids=sorted({row['role_id'] for row in rows})
        db=get_db()
        if not ids or not db.execute("SELECT 1 FROM sqlite_master WHERE name='role_representations'").fetchone():
            return {}
        labels={};territories={}
        for r in db.execute('''SELECT role_id,territory_name,source_certainty
            FROM role_representations WHERE role_id IN ('''+','.join('?' for _ in ids)+''')
            ORDER BY source_paragraph,representation_id''',ids):
            items=territories.setdefault(r['role_id'],{})
            name=r['territory_name']
            items[name]=items.get(name,False) or r['source_certainty']=='asserted'
        for role_id,items in territories.items():
            labels[role_id]=[name if asserted else name+' (?)' for name,asserted in items.items()]
        return labels

    def person_context(person_id):
        db = get_db()
        row = db.execute('SELECT * FROM persons WHERE person_id=?',(person_id,)).fetchone()
        if row is None:
            abort(404)
        data = dict(row)
        for key in list(data):
            if key.endswith('_json'):
                data[key[:-5]] = json.loads(data[key])
        record = data['record']
        sections = [(key,record.get(key,[])) for key in ('edukacja','majątek','źródła','inne_informacje')]
        offices = db.execute('''SELECT * FROM person_offices WHERE person_id=?
            ORDER BY COALESCE(dating_year_min,dating_year_max) IS NULL,
                COALESCE(dating_year_min,dating_year_max),COALESCE(dating_year_max,dating_year_min),position''',(person_id,)).fetchall()
        titles = db.execute('SELECT * FROM person_titles WHERE person_id=? ORDER BY kind,position',(person_id,)).fetchall()
        roles = db.execute('''SELECT er.*,e.name AS event_name,e.place AS event_place,e.date_raw AS event_date_raw,
            e.occurrence_status,e.date_start AS event_date_start,e.year_start AS event_year_start,
            e.source_paragraph AS event_source_paragraph FROM person_event_roles er LEFT JOIN events e ON e.event_id=er.event_id
            WHERE er.person_id=? ORDER BY COALESCE(e.year_start,er.year_start,9999),COALESCE(e.source_paragraph,99999),er.position''',(person_id,)).fetchall()
        labels=representation_labels(roles)
        roles=[dict(row,representations=labels.get(row['role_id'],[]),participation_notes=participation_notes(row)) for row in roles]
        return dict(person=data,record=record,sections=sections,offices=offices,titles=titles,roles=roles)

    @app.route('/persons/<int:person_id>')
    def person(person_id):
        context=person_context(person_id)
        view='timeline' if request.args.get('view')=='timeline' else 'tables'
        navigation = None
        catalogue = request.args.get('catalogue', '')
        if catalogue and len(catalogue) <= 4000:
            values = {k:v[-1] for k,v in parse_qs(catalogue).items()}
            result = index(navigation_args=values)
            ids = result['ids']
            if person_id in ids:
                position = ids.index(person_id)
                catalogue = urlencode({k:v for k,v in result['filters'].items() if v})
                def adjacent_url(offset):
                    target = position + offset
                    if not 0 <= target < len(ids):
                        return None
                    return url_for('person',person_id=ids[target],catalogue=catalogue,view=view)
                navigation = dict(previous=adjacent_url(-1), next=adjacent_url(1),
                    back=url_for('index',**{k:v for k,v in result['filters'].items() if v},page=position//24+1),
                    position=position+1,total=len(ids),active=result['active'])
        def career_url(selected):
            values = dict(person_id=person_id,view=selected)
            if navigation:
                values['catalogue'] = catalogue
            return url_for('person',**values)
        return render_template('person.html',**context,career_view=view,navigation=navigation,career_url=career_url,
                               career=build_career(context['offices'],context['roles']) if view=='timeline' else [])

    @app.route('/persons/<int:person_id>/pdf')
    def person_pdf(person_id):
        context = person_context(person_id)
        stream = build_person_pdf(context,app_title=TITLE,format_source=format_source,certainty=CERTAINTY)
        filename = (secure_filename(context['person']['name']) or 'biogram')+'.pdf'
        response = send_file(stream,mimetype='application/pdf',as_attachment=True,download_name=filename)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/persons/<int:person_id>/docx')
    def person_docx(person_id):
        context = person_context(person_id)
        stream = build_person_docx(context, app_title=TITLE, format_source=format_source, certainty=CERTAINTY)
        filename = (secure_filename(context['person']['name']) or 'biogram')+'.docx'
        response = send_file(stream, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                             as_attachment=True, download_name=filename)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/summaries')
    def summaries():
        db=get_db()
        include_uncertain=request.args.get('include_uncertain')=='1'
        selected=request.args.get('territory','').strip()
        events_by_id={r['event_id']:dict(r) for r in db.execute('SELECT * FROM events')}
        rows=db.execute('''SELECT er.*,p.name,p.surname,p.birth_date_raw,p.death_date_raw
            FROM person_event_roles er JOIN persons p USING(person_id)
            ORDER BY COALESCE(p.surname,p.name) COLLATE POLISH,p.name COLLATE POLISH,er.position''').fetchall()
        event_ranking,person_ranking=ranked_participations(rows,events_by_id,include_uncertain)
        event_ranking.sort(key=lambda e:(-e['people_count'],e['year_start'] or 9999,e['source_paragraph']))
        person_ranking.sort(key=lambda p:(-p['event_count'],polish_key(p['surname']),polish_key(p['name']),p['person_id']))
        event_codes={}
        for r in db.execute('SELECT DISTINCT event_id,normalized_code FROM event_code_matches WHERE event_id IS NOT NULL ORDER BY normalized_code'):
            event_codes.setdefault(r['event_id'],[]).append(r['normalized_code'])
        territories=set();role_territories={}
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='role_representations'").fetchone():
            for r in db.execute('SELECT role_id,territory_name FROM role_representations'):
                parts=territory_parts(r['territory_name'])
                territories.update(parts)
                role_territories.setdefault(r['role_id'],set()).update(fold(p).casefold() for p in parts)
        territories=sorted(territories,key=polish_key)
        canonical={fold(t).casefold():t for t in territories}
        error=None
        if selected:
            selected=canonical.get(fold(selected).casefold(),'') if len(selected)<=100 else ''
            if not selected:
                error='Wybierz obszar z listy.'
        area_rows={}
        if selected:
            for r in rows:
                if r['role']=='poseł' and r['event_id'] in events_by_id and fold(selected).casefold() in role_territories.get(r['role_id'],set()):
                    area_rows.setdefault(r['event_id'],[]).append(r)
        area_events=[]
        for eid,members in area_rows.items():
            area_events.append(dict(event=events_by_id[eid],people=role_groups(members).get('poseł',[])))
        area_events.sort(key=lambda r:(r['event']['year_start'] or 9999,r['event']['source_paragraph']))
        return render_template('summaries.html',event_ranking=event_ranking[:10],person_ranking=person_ranking[:10],
            include_uncertain=include_uncertain,event_codes=event_codes,territories=territories,
            selected_territory=selected,area_events=area_events,error=error),400 if error else 200

    @app.route('/events')
    def events(export=False):
        db = get_db()
        view = request.args.get('view', 'list')
        if view not in ('list', 'cards'):
            view = 'list'
        code = request.args.get('code','').strip()
        kind = request.args.get('type','')
        kinds = sorted({r[0] for r in db.execute('SELECT kind FROM events UNION SELECT event_type FROM person_event_roles') if r[0]})
        start,end = request.args.get('year_from','').strip(),request.args.get('year_to','').strip()
        error = None
        conditions,params = [],[]
        if len(code)>100 or kind and kind not in kinds:
            error = 'Niepoprawny filtr wydarzeń.'
        if code:
            literal = '%'+code.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            conditions.append("(e.heading_raw LIKE ? ESCAPE '\\' OR e.place LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM event_code_matches m WHERE m.event_id=e.event_id AND m.event_code_raw LIKE ? ESCAPE '\\'))")
            params.extend([literal]*3)
        if kind:
            conditions.append('e.kind=?');params.append(kind)
        try:
            first,last = int(start) if start else None,int(end) if end else None
            if any(y is not None and not 1400<=y<=1900 for y in (first,last)) or (first and last and first>last):
                raise ValueError()
            if first:
                conditions.append('e.year_end>=?');params.append(first)
            if last:
                conditions.append('e.year_start<=?');params.append(last)
        except ValueError:
            error = 'Podaj poprawny zakres lat (1400–1900).'
        where = 'WHERE '+' AND '.join(conditions) if conditions else ''
        rows = [] if error else db.execute(f'''SELECT e.*,
            (SELECT count(DISTINCT person_id) FROM person_event_roles r WHERE r.event_id=e.event_id) AS people_count,
            (SELECT count(*) FROM person_event_roles r WHERE r.event_id=e.event_id) AS mentions_count
            FROM events e {where} ORDER BY e.year_start,e.source_paragraph''',params).fetchall()
        event_codes = {}
        for match in db.execute('''SELECT DISTINCT event_id,normalized_code FROM event_code_matches
            WHERE event_id IS NOT NULL ORDER BY normalized_code'''):
            event_codes.setdefault(match['event_id'],[]).append(match['normalized_code'])
        filters = dict(code=code,type=kind,year_from=start,year_to=end)
        query_active=bool(code or kind or start or end)
        if export and not query_active:
            abort(400)
        if export and not error:
            stream=build_events_xlsx(rows,event_codes,translate=translate)
            response=send_file(stream,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               as_attachment=True,download_name='sejmy-i-zjazdy-wyniki.xlsx')
            response.headers['Cache-Control']='no-store'
            return response
        export_url=url_for('events_xlsx',**{k:v for k,v in filters.items() if v})
        def view_url(selected):
            return url_for('events', **{k:v for k,v in filters.items() if v}, view=selected)
        return render_template('events.html',events=rows,event_codes=event_codes,kinds=kinds,error=error,
            filters=filters,view=view,view_url=view_url,query_active=query_active,export_url=export_url),400 if error else 200

    @app.route('/events/export.xlsx')
    def events_xlsx():
        return events(export=True)

    def role_groups(rows):
        labels=representation_labels(rows)
        representations={}
        qualifications={}
        for row in rows:
            notes=qualifications.setdefault((row['role'],row['person_id']),[])
            for note in participation_notes(row):
                if note not in notes:notes.append(note)
            items=representations.setdefault((row['role'],row['person_id']),[])
            for label in labels.get(row['role_id'],[]):
                if label not in items:items.append(label)
        ids = sorted({row['person_id'] for row in rows})
        offices = {}
        seen_offices = {}
        if ids:
            for office in get_db().execute('''SELECT person_id,name FROM person_offices
                WHERE person_id IN ('''+','.join('?' for _ in ids)+''')
                ORDER BY COALESCE(dating_year_min,dating_year_max) IS NULL,
                    COALESCE(dating_year_min,dating_year_max),position''',ids):
                name = office['name'].strip()
                key = ' '.join(name.split()).casefold()
                seen = seen_offices.setdefault(office['person_id'],set())
                if name and key not in seen:
                    offices.setdefault(office['person_id'],[]).append(name)
                    seen.add(key)
        groups = {}
        seen_people = set()
        for row in rows:
            key = row['role'],row['person_id']
            if key not in seen_people:
                person = dict(row)
                person['life_years'] = life_years(row)
                person['offices'] = offices.get(row['person_id'],[])
                person['representations']=representations.get(key,[])
                person['participation_notes']=distinct_explanations(qualifications.get(key,[]))
                groups.setdefault(row['role'],[]).append(person)
                seen_people.add(key)
        return dict(sorted(groups.items(),key=lambda pair:list(ROLE_NAMES).index(pair[0]) if pair[0] in ROLE_NAMES else len(ROLE_NAMES)))

    def event_context(event_id):
        db = get_db()
        row = db.execute('SELECT * FROM events WHERE event_id=?',(event_id,)).fetchone()
        if row is None:
            abort(404)
        event = dict(row)
        event['codes'] = [r['normalized_code'] for r in db.execute('''SELECT DISTINCT normalized_code
            FROM event_code_matches WHERE event_id=? ORDER BY normalized_code''',(event_id,))]
        for key in ('sessions','sources','context'):
            event[key] = json.loads(event[key+'_json'])
        rows = db.execute('''SELECT er.*,p.name,p.surname,p.birth_date_raw,p.death_date_raw FROM person_event_roles er
            JOIN persons p ON p.person_id=er.person_id WHERE er.event_id=?
            ORDER BY COALESCE(p.surname,p.name) COLLATE POLISH,p.name COLLATE POLISH,er.position''',(event_id,)).fetchall()
        return dict(event=event,groups=role_groups(rows),
            people_count=len({r['person_id'] for r in rows}),candidates=[])

    @app.route('/events/<event_id>')
    def event_detail(event_id):
        return render_template('event.html', **event_context(event_id))

    @app.route('/events/<event_id>/pdf')
    def event_pdf(event_id):
        context = event_context(event_id)
        stream = build_event_pdf(context, app_title=translate(TITLE),
                                 role_names=ROLE_NAMES, translate=translate)
        event = context['event']
        label = '-'.join(event['codes']) or event_id
        filename = secure_filename(event['name']+'-'+label)+'.pdf'
        response = send_file(stream, mimetype='application/pdf', as_attachment=True,
                             download_name=filename)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/events/<event_id>/docx')
    def event_docx(event_id):
        context = event_context(event_id)
        stream = build_event_docx(context, app_title=translate(TITLE), role_names=ROLE_NAMES, translate=translate)
        event = context['event']
        label = '-'.join(event['codes']) or event_id
        filename = (secure_filename(event['name']+'-'+label) or 'wydarzenie')+'.docx'
        response = send_file(stream, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                             as_attachment=True, download_name=filename)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/events/<event_id>/xlsx')
    def event_xlsx(event_id):
        context = event_context(event_id)
        stream = build_event_xlsx(context, app_title=translate(TITLE), role_names=ROLE_NAMES, translate=translate)
        event = context['event']
        label = '-'.join(event['codes']) or event_id
        filename = (secure_filename(event['name']+'-'+label) or 'wydarzenie')+'.xlsx'
        response = send_file(stream, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             as_attachment=True, download_name=filename)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/events/detail')
    def event():
        code,kind = request.args.get('code',''),request.args.get('type','')
        if not code or len(code)>100 or len(kind)>100:
            abort(404)
        db = get_db()
        match = db.execute('SELECT * FROM event_code_matches WHERE event_code_raw=? AND event_type_raw=?',(code,kind)).fetchone()
        if match and match['event_id']:
            return redirect(url_for('event_detail',event_id=match['event_id']))
        rows = db.execute('''SELECT er.*,p.name,p.surname,p.birth_date_raw,p.death_date_raw FROM person_event_roles er
            JOIN persons p ON p.person_id=er.person_id WHERE er.event_code_raw=? AND COALESCE(er.event_type,'')=? AND er.event_id IS NULL
            ORDER BY COALESCE(p.surname,p.name) COLLATE POLISH,p.name COLLATE POLISH,er.position''',(code,kind)).fetchall()
        if not rows:
            linked = db.execute("SELECT DISTINCT event_id FROM person_event_roles WHERE event_code_raw=? AND COALESCE(event_type,'')=? AND event_id IS NOT NULL",(code,kind)).fetchall()
            if len(linked)==1:
                return redirect(url_for('event_detail',event_id=linked[0]['event_id']))
            abort(404)
        candidates = []
        if match:
            for event_id in json.loads(match['candidates_json']):
                candidate = db.execute('SELECT * FROM events WHERE event_id=?',(event_id,)).fetchone()
                if candidate:
                    candidates.append(candidate)
        return render_template('event.html',event=None,code=code,kind=kind,candidates=candidates,
            groups=role_groups(rows),people_count=len({r['person_id'] for r in rows}))

    @app.errorhandler(404)
    def not_found(error):
        return render_template('error.html',message='Nie znaleziono biogramu ani strony pod tym adresem.',code=404),404

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,help='Ścieżka do bazy; domyślnie BIOGRAMS_DATABASE lub web/instance/biograms.sqlite.')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8767)
    args = parser.parse_args()
    if not 1024<=args.port<=65535:
        parser.error('Niepoprawny port.')
    app = create_app({'DATABASE':args.database} if args.database is not None else None)
    print(f'Katalog biogramów: http://{args.host}:{args.port}',flush=True)
    app.run(host=args.host,port=args.port,debug=False)


if __name__=='__main__':
    main()
