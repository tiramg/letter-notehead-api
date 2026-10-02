"""Create progressive-learning MusicXML using notehead-text pitch letters."""
from pathlib import Path
import io, zipfile
import xml.etree.ElementTree as ET

VALID_MODES = {'all', 'guide', 'none'}

def add_letter_noteheads(xml_bytes,title=None,composer=None,clean_layout=True,label_mode='all'):
    if label_mode not in VALID_MODES:
        raise ValueError(f'Unknown label mode: {label_mode}')
    root=ET.fromstring(xml_bytes); changed=0
    if clean_layout:
        # Scanner coordinates describe the source page, not an ideal new engraving.
        for element in root.iter():
            for attr in ('default-x','default-y','relative-x','relative-y','width'):
                element.attrib.pop(attr,None)
        for measure in root.iter('measure'):
            for item in list(measure.findall('print')):
                keep={k:v for k,v in item.attrib.items() if k in ('new-system','new-page')}
                if not keep:
                    measure.remove(item)
                else:
                    item.attrib.clear(); item.attrib.update(keep)
                    for child in list(item): item.remove(child)
        defaults=root.find('defaults')
        if defaults is not None: root.remove(defaults)
    if title:
        work=root.find('work')
        if work is None: work=ET.Element('work'); root.insert(0,work)
        wt=work.find('work-title')
        if wt is None: wt=ET.SubElement(work,'work-title')
        wt.text=title
    if composer:
        identification=root.find('identification')
        if identification is None:
            identification=ET.Element('identification'); root.insert(1 if root.find('work') is not None else 0,identification)
        creator=identification.find("creator[@type='composer']")
        if creator is None: creator=ET.SubElement(identification,'creator',{'type':'composer'})
        creator.text=composer
    for part_name in root.findall('part-list/score-part/part-name'):
        part_name.set('print-object','no'); part_name.text=' '
    for abbreviation in root.findall('part-list/score-part/part-abbreviation'):
        abbreviation.set('print-object','no'); abbreviation.text=' '
    for measure in root.iter('measure'):
        first_event_seen=set(); current_event_selected={}
        for note in measure.findall('note'):
            old=note.find('notehead-text')
            if old is not None: note.remove(old)
            pitch=note.find('pitch')
            if pitch is None or note.find('rest') is not None: continue
            step=pitch.findtext('step')
            if not step: continue
            voice=note.findtext('voice') or '1'
            is_chord=note.find('chord') is not None
            if not is_chord:
                selected=voice not in first_event_seen
                first_event_seen.add(voice)
                current_event_selected[voice]=selected
            else:
                selected=current_event_selected.get(voice, False)
            should_label=(label_mode=='all' or (label_mode=='guide' and selected))
            if not should_label: continue
            item=ET.Element('notehead-text'); text=ET.SubElement(item,'display-text'); text.text=step
            children=list(note); insert_at=len(children)
            # MusicXML order places notehead-text after notehead and before staff/beam/notations.
            for tag in ('staff','beam','notations','lyric','play','listen'):
                found=note.find(tag)
                if found is not None: insert_at=min(insert_at,list(note).index(found))
            note.insert(insert_at,item); changed+=1
    declaration=b'<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype=b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0.3 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'
    return declaration+doctype+ET.tostring(root,encoding='utf-8'),changed

def convert_mxl(source,destination,title=None,composer=None,clean_layout=True,label_mode='all'):
    source=Path(source); destination=Path(destination)
    with zipfile.ZipFile(source) as zin:
        names=zin.namelist(); score=next(n for n in names if n.endswith('.xml') and not n.startswith('META-INF/'))
        converted,count=add_letter_noteheads(zin.read(score),title,composer,clean_layout,label_mode)
        with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as zout:
            for name in names: zout.writestr(name,converted if name==score else zin.read(name))
    return count

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('source'); p.add_argument('destination'); p.add_argument('--title'); p.add_argument('--composer'); p.add_argument('--keep-layout',action='store_true'); p.add_argument('--mode',choices=sorted(VALID_MODES),default='all'); args=p.parse_args()
    print(f'Added {convert_mxl(args.source,args.destination,args.title,args.composer,not args.keep_layout,args.mode)} pitch labels ({args.mode})')
