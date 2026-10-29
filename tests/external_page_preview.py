import asyncio, json, pathlib
from playwright.async_api import async_playwright

URL="https://europe-vacation-planner-2026.onrender.com/?imageSource=external&previewCheck=1"
KEYS=["2026-11-"+str(n).zfill(2) for n in range(21,31)]+["2026-12-"+str(n).zfill(2) for n in range(1,7)]

async def check_browser(p,label,engine,mobile):
  browser=await getattr(p,engine).launch(headless=True)
  try:
    page=await browser.new_page(viewport={"width":390 if mobile else 1280,"height":844 if mobile else 800},is_mobile=mobile,has_touch=mobile)
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    response=await page.goto(URL,wait_until="domcontentloaded",timeout=45000)
    await page.wait_for_selector(".days .cell.trip",timeout=20000)
    await page.wait_for_function("""()=>[...document.querySelectorAll('.cell.trip')]
      .every(el=>getComputedStyle(el).backgroundImage.includes('wikimedia.org'))""",timeout=40000)
    days=await page.locator(".days .cell.trip").count()
    report={"status":response.status,"days":days,"checks":[],"errors":errors}
    for key in KEYS:
      await page.evaluate("(key)=>openDay(key)",key)
      await page.wait_for_function("""()=>[...document.querySelectorAll('#tasks .journey-photo')].length>0
        && [...document.querySelectorAll('#tasks .journey-photo')].every(img=>img.complete&&img.naturalWidth>0)""",timeout=30000)
      entry=await page.evaluate("""key=>({date:key,images:[...document.querySelectorAll('#tasks .journey-photo')].map(img=>({
        src:img.currentSrc,visible:getComputedStyle(img).opacity==='1'&&getComputedStyle(img).display!=='none',
        decoded:img.naturalWidth>0})),modalPhoto:document.querySelector('#modalPhoto')?.currentSrc})""",key)
      report["checks"].append(entry)
    report["totalActivities"]=sum(len(x["images"]) for x in report["checks"])
    report["externalActivities"]=sum(1 for x in report["checks"] for i in x["images"] if "wikimedia.org" in i["src"] and i["decoded"] and i["visible"])
    report["failedActivities"]=[{"date":x["date"],"src":i["src"],"visible":i["visible"]} for x in report["checks"] for i in x["images"] if not ("wikimedia.org" in i["src"] and i["decoded"] and i["visible"])]
    report["externalModalPhotos"]=sum("wikimedia.org" in (x["modalPhoto"] or "") for x in report["checks"])
    return report
  finally:
    await browser.close()

async def main():
  result={}
  async with async_playwright() as p:
    for label,engine,mobile in [("mobile-webkit","webkit",True),("mobile-chromium","chromium",True),("desktop-chromium","chromium",False)]:
      try:result[label]=await check_browser(p,label,engine,mobile)
      except Exception as e:result[label]={"error":str(e)}
      print(label,{k:v for k,v in result[label].items() if k!="checks"},flush=True)
  path=pathlib.Path("test-results");path.mkdir(exist_ok=True)
  (path/"external-page-preview.json").write_text(json.dumps(result,indent=2))

if __name__=="__main__":asyncio.run(main())
