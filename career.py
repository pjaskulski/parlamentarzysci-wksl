"""Chronologiczny widok istniejących urzędów i funkcji, bez odtwarzania dat."""
from collections import defaultdict
import re


def build_career(offices, roles):
    years=defaultdict(list)
    for row in offices:
        office=dict(row)
        year=office.get('dating_year_min') or office.get('dating_year_max')
        status=None
        if office.get('certainty')=='odrzucone_lub_prostowane':
            raw=office.get('description_raw') or ''
            if re.search('niedoszł|nie objął|nie przyjął',raw,re.I):status='Urząd nieobjęty'
            elif re.search('rzekom',raw,re.I):status='Urząd przypisany błędnie'
        years[year].append(dict(kind='office',office=office,status=status))
    events={}
    for row in roles:
        role=dict(row)
        key=role.get('event_id') or (role.get('event_code_raw'),role.get('event_type'))
        if key not in events:
            events[key]=dict(kind='event',event=role,roles=[],codes=[],sort_date=role.get('event_date_start') or '',
                             year=role.get('event_year_start') or role.get('year_start'))
        item=events[key]
        if role['event_code_raw'] not in item['codes']:item['codes'].append(role['event_code_raw'])
        # Zachowaj wszystkie funkcje; powtórzone wzmianki o tej samej funkcji scal.
        entry=next((r for r in item['roles'] if r['role']==role['role']),None)
        if entry is None:
            entry=dict(role=role['role'],representations=[],participation_notes=[]);item['roles'].append(entry)
        for field in ['representations','participation_notes']:
            for value in role.get(field,[]):
                if value not in entry[field]:entry[field].append(value)
    for item in events.values():
        notes=[n for r in item['roles'] for n in r['participation_notes']]
        item['uncertain']=any(n['kind']!='info' or n['label'] in ['Nie uczestniczył w posiedzeniach senatu','Nieobecny na obradach'] for n in notes)
        years[item['year']].append(item)
    result=[]
    for year in sorted(years,key=lambda y:(y is None,y or 0)):
        # Kolejność urzędów bez dat dziennych nie oznacza następstwa wobec sejmów.
        items=years[year]
        items.sort(key=lambda x:(x['kind']=='event',x.get('sort_date',''),x.get('event',{}).get('event_source_paragraph') or 0))
        result.append(dict(year=year,items=items))
    return result
