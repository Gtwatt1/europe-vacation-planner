#!/usr/bin/env python3
"""Verify original online images and potential Wikimedia CDN replacements in real browsers.
Does not modify the production site.
"""
import ast, asyncio, json, os, pathlib, re, subprocess, urllib.parse, urllib.request
from playwright.async_api import async_playwright

ROOT=pathlib.Path(__file__).resolve().parent.parent
HTML=(ROOT/"index.html").read_text(encoding="utf-8")
FETCH=(ROOT/"scripts/fetch_images.py").read_text(encoding="utf-8")
astree=ast.parse(FETCH)
assigns={}
for n in astree.body:
  if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
    if n.targets[0].id in ("places","mapping","node"):
      assigns[n.targets[0].id]=ast.literal_eval(n.value)
places,mapping,node=assigns["places"],assigns["mapping"],assigns["node"]
trip=json.loads(subprocess.check_output(["node","-e",node],cwd=ROOT,text=True))
def get_title(label,day):
  for pattern,title in mapping:
    if re.search(pattern,label,re.I):return title
  return places[day]

def extract_js(name):
  match=re.search(r"const "+name+r"=(\{.*?\});",HTML,flags=re.S)
  if not match:raise RuntimeError("Missing "+name)
  return json.loads(match.group(1))
dayPhotos=extract_js("dayPhotos")
activityPhotos=extract_js("activityPhotos")
# The old onlinePhotos structure contains single-quoted JS strings; collect HTTPS URLs directly.
online_section=HTML.split("const onlinePhotos=",1)[1].split("function setTravelPhoto",1)[0]
old_links={u for u in re.findall(r"https://images\.unsplash\.com/[^'\"\s]+",online_section)}
old_links |= set(dayPhotos.values())
for arr in activityPhotos.values():old_links.update(arr)

HEADERS={"User-Agent":"EuropeVacationPlanner/1.0 image-test (github.com/Gtwatt1/europe-vacation-planner)"}
def get_json(url):
  req=urllib.request.Request(url,headers=HEADERS)
  with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
source_cache={}
def source_for(title):
  if title not in source_cache:
    try:
      url=("https://en.wikipedia.org/w/api.php?action=query&format=json&formatversion=2"
           "&redirects=1&prop=pageimages&piprop=thumbnail&pithumbsize=1000&titles="+urllib.parse.quote(title))
      data=get_json(url)
      source_cache[title]=next((p.get("thumbnail",{}).get("source") for p in data.get("query",{}).get("pages",[]) if p.get("thumbnail")),None)
    except Exception as exc:
      print("lookup failure",title,str(exc)[:150],flush=True)
      source_cache[title]=None
  return source_cache[title]

targets={}
for key,d in trip.items():
  targets[key]=[places[key]]
  for i,(_,label) in enumerate(d["items"]):
    t=get_title(label,key)
    targets[key+"-"+str(i)]=list(dict.fromkeys([t,places[key]]))
manifest={}
for key,titles in targets.items():
  for title in titles:
    src=source_for(title)
    if src:
      manifest[key]=src
      break

async def check_images(page,items):
  return await page.evaluate("""async entries=>{
   const result=[];
   for(let i=0;i<entries.length;i+=12){
     const batch=await Promise.all(entries.slice(i,i+12).map(([key,url])=>new Promise(resolve=>{
       const im=new Image();let settled=false;
       const finish=(okay,why)=>{if(!settled){settled=true;resolve({key,url,loaded:okay,width:im.naturalWidth,reason:why})}};
       im.onload=()=>finish(im.naturalWidth>0,'loaded');
       im.onerror=()=>finish(false,'onerror');
       im.src=url;
       setTimeout(()=>finish(false,'timeout'),12000);
     })));
     result.push(...batch);
   }
   return result;
  }""",list(items.items()))

async def main():
  out={"candidates":len(manifest),"expected":len(targets),"lookup_missing":[k for k in targets if k not in manifest],
       "historical_unsplash_unique":len(old_links),"checks":{}}
  async with async_playwright() as p:
    for label,engine,mobile in [("mobile-webkit","webkit",True),("mobile-chromium","chromium",True),("desktop-chromium","chromium",False)]:
      browser=None
      try:
        browser=await getattr(p,engine).launch(headless=True)
        page=await browser.new_page(viewport={"width":390 if mobile else 1280,"height":844 if mobile else 800},is_mobile=mobile,has_touch=mobile)
        await page.goto("https://europe-vacation-planner-2026.onrender.com/?external-image-check=1",wait_until="domcontentloaded",timeout=45000)
        remote=await check_images(page,manifest)
        old=await check_images(page,{str(i):u for i,u in enumerate(sorted(old_links))})
        out["checks"][label]={
          "remote_pass":sum(x["loaded"] for x in remote),"remote_total":len(remote),
          "remote_failed":[x for x in remote if not x["loaded"]],
          "old_unsplash_pass":sum(x["loaded"] for x in old),"old_unsplash_total":len(old),
          "old_unsplash_failed":[x for x in old if not x["loaded"]]}
        print(label, {k:v for k,v in out["checks"][label].items() if not isinstance(v,list)},flush=True)
      except Exception as e:
        out["checks"][label]={"error":str(e)}
      finally:
        if browser:await browser.close()
  resultdir=ROOT/"test-results";resultdir.mkdir(exist_ok=True)
  (resultdir/"external-image-audit.json").write_text(json.dumps(out,indent=2))
  (resultdir/"external-image-candidates.json").write_text(json.dumps(manifest,indent=2))
  print(json.dumps({k:v for k,v in out.items() if k!="checks"},indent=2),flush=True)
  for k,v in out["checks"].items():print(k, {key:value for key,value in v.items() if not isinstance(value,list)},flush=True)

if __name__=="__main__":asyncio.run(main())
