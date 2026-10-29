#!/usr/bin/env python3
"""Download and validate site-owned travel photos from Wikipedia."""
import json, pathlib, re, subprocess, urllib.parse, urllib.request, io, time
from PIL import Image, ImageOps

ROOT=pathlib.Path(__file__).resolve().parent.parent
html=(ROOT/'index.html').read_text()
node=r"""
const fs=require('fs'),vm=require('vm');
const s=fs.readFileSync('index.html','utf8');
const block=s.slice(s.indexOf('const D='),s.indexOf('const stays='));
const data=vm.runInNewContext(block+';JSON.stringify(trip)');
process.stdout.write(data);
"""
trip=json.loads(subprocess.check_output(['node','-e',node],cwd=ROOT,text=True))
places={
 '2026-11-21':'Toronto Pearson International Airport',
 '2026-11-22':'Amsterdam',
 '2026-11-23':'Rijksmuseum',
 '2026-11-24':'Antwerp',
 '2026-11-25':'Amsterdam Centraal station',
 '2026-11-26':'Eiffel Tower',
 '2026-11-27':'Louvre',
 '2026-11-28':'Palais Garnier',
 '2026-11-29':'Palace of Versailles',
 '2026-11-30':'Strasbourg Cathedral',
 '2026-12-01':'Gare du Nord',
 '2026-12-02':'Big Ben',
 '2026-12-03':'Tower Bridge',
 '2026-12-04':'Newcastle upon Tyne',
 '2026-12-05':'Tynemouth',
 '2026-12-06':'Heathrow Airport'
}
mapping=[
 (r'Rijksmuseum','Rijksmuseum'),(r'Van Gogh','Van Gogh Museum'),(r'Anne Frank','Anne Frank House'),
 (r'Jordaan|Nine Streets','Jordaan'),(r'De Pijp|Albert Cuyp','Albert Cuyp Market'),
 (r'canal','Canals of Amsterdam'),(r'Dam Square','Dam Square'),
 (r'Antwerp Central','Antwerpen-Centraal railway station'),(r'cathedral.*Antwerp','Cathedral of Our Lady (Antwerp)'),
 (r'Grote Markt','Grote Markt (Antwerp)'),(r'Strasbourg Cathedral','Strasbourg Cathedral'),
 (r'Petite France','Petite France, Strasbourg'),(r'Christmas.market','Strasbourg'),
 (r'Gare du Nord','Gare du Nord'),(r'Eiffel Tower','Eiffel Tower'),(r'Trocadéro','Trocadéro'),
 (r'Arc de Triomphe|Champs','Arc de Triomphe'),(r'Seine','Seine'),
 (r'Louvre','Louvre'),(r'Tuileries','Tuileries Garden'),(r'Montmartre|Sacré','Sacré-Cœur, Paris'),
 (r'Palais Garnier','Palais Garnier'),(r'Galeries Lafayette','Galeries Lafayette'),
 (r'Place des Vosges|Le Marais','Place des Vosges'),(r'Versailles','Palace of Versailles'),
 (r'King.s Cross','London King\'s Cross railway station'),(r'St Pancras','St Pancras railway station'),
 (r'Covent Garden','Covent Garden'),(r'Chinatown|Soho','Chinatown, London'),
 (r'Westminster','Westminster Abbey'),(r'Big Ben','Big Ben'),
 (r'Buckingham','Buckingham Palace'),(r'London Eye|South Bank','London Eye'),
 (r'Tower of London','Tower of London'),(r'Tower Bridge','Tower Bridge'),
 (r'Borough Market','Borough Market'),(r'Sky Garden','20 Fenchurch Street'),
 (r'Newcastle|Quayside|Millennium Bridge','Newcastle upon Tyne'),
 (r'Tynemouth','Tynemouth'),(r'Heathrow','Heathrow Airport'),(r'Pearson|Toronto','Toronto Pearson International Airport'),
 (r'Amsterdam Centraal','Amsterdam Centraal station'),(r'Belgian|Antwerp','Antwerp'),
 (r'Paris','Paris'),(r'London','London'),(r'train|TGV|Eurostar','Rail transport'),
 (r'flight|airport|depart|land|connecting','Airport'),(r'restaurant|dinner|breakfast|lunch|café','Restaurant')
]
def get_title(label,day):
 for pat,title in mapping:
  if re.search(pat,label,re.I):return title
 return places[day]

headers={'User-Agent':'EuropeVacationPlanner/1.0 (https://github.com/Gtwatt1/europe-vacation-planner; image-fetcher)'}
def fetch(url):
 req=urllib.request.Request(url,headers=headers)
 with urllib.request.urlopen(req,timeout=25) as r:return r.read()

cache={}
def photo(title):
 if title in cache:return cache[title]
 api='https://en.wikipedia.org/w/api.php?format=json&formatversion=2&action=query&redirects=1&prop=pageimages&piprop=thumbnail&pithumbsize=1000&titles='+urllib.parse.quote(title)
 try:
  data=json.loads(fetch(api))
  pages=data.get('query',{}).get('pages',[])
  src=next((x['thumbnail']['source'] for x in pages if x.get('thumbnail')),None)
  if src:
   raw=fetch(src)
   im=Image.open(io.BytesIO(raw));im.load()
   if im.width>=160 and im.height>=120:
    im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1000,750))
    out=io.BytesIO();im.save(out,format='JPEG',quality=77,optimize=True)
    cache[title]=out.getvalue();return cache[title]
 except Exception as ex:print('SOURCE FAIL',title,str(ex)[:120])
 cache[title]=None;return None

dest=ROOT/'images';dest.mkdir(exist_ok=True)
manifest={};fail=[]
for day,d in trip.items():
 for i,(when,label) in enumerate(d['items']):
  title=get_title(label,day)
  fallback=places[day]
  blob=photo(title) or (photo(fallback) if title!=fallback else None)
  path='images/'+day+'-'+str(i)+'.jpg'
  if blob:(ROOT/path).write_bytes(blob);manifest[day+'-'+str(i)]=path
  else:fail.append((day,i,label))
 blob=photo(places[day])
 if blob:
  path='images/'+day+'.jpg';(ROOT/path).write_bytes(blob);manifest[day]=path
 else:fail.append((day,'calendar',places[day]))
(ROOT/'images/manifest.json').write_text(json.dumps(manifest,indent=2))
print('VERIFIED',len(manifest),'files; missing',len(fail),fail)
if len(manifest)<16:raise SystemExit('Insufficient verified images')
