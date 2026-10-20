"""Rankingi liczą unikalne pary osoby i rozpoznanego wydarzenia."""
from collections import defaultdict
import json

try:
    from .participation import display_participation_notes
except ImportError:
    from participation import display_participation_notes


def ranked_participations(rows, events, include_uncertain=False):
    pairs=set()
    people={}
    for raw in rows:
        r=dict(raw)
        event=events.get(r['event_id'])
        if not event or event['occurrence_status']!='held':
            continue
        if r['certainty']=='odrzucone_lub_prostowane' or r['attendance'] in ('nieobecny','mandat_nieuznany'):
            continue
        record=r.get('record_json') or {}
        if isinstance(record,str):
            record=json.loads(record)
        if r['role']=='senator' and record.get('nie_zasiadał_w_radzie'):
            continue
        if not include_uncertain and (
            r['certainty']=='niepewne' or r['attendance']=='nieustalona'
            or any(n['kind']!='info' for n in display_participation_notes(r))
        ):
            continue
        pairs.add((r['person_id'],r['event_id']))
        people[r['person_id']]=dict(person_id=r['person_id'],name=r['name'],surname=r.get('surname') or r['name'])
    by_event=defaultdict(set)
    by_person=defaultdict(set)
    for pid,eid in pairs:
        by_event[eid].add(pid)
        by_person[pid].add(eid)
    event_counts=[dict(events[eid],people_count=len(ids)) for eid,ids in by_event.items()]
    person_counts=[dict(people[pid],event_count=len(ids)) for pid,ids in by_person.items()]
    return event_counts,person_counts
