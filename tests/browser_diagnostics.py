import asyncio, json, pathlib, os
from playwright.async_api import async_playwright

BASE = "https://europe-vacation-planner-2026.onrender.com/"
VERSION = os.getenv("GITHUB_SHA", "manual")

async def inspect(page, label):
  errors=[]; failed=[]
  page.on("pageerror",lambda err: errors.append(str(err)))
  page.on("requestfailed",lambda req: failed.append({"url":req.url[:180],"reason":req.failure}))
  response=None
  ready=False
  for attempt in range(20):
    response=await page.goto(BASE+"?image-smoke="+VERSION+"&attempt="+str(attempt),wait_until="domcontentloaded",timeout=45000)
    if "image.loading='eager'" in await page.content():
      ready=True;break
    await page.wait_for_timeout(3500)
  if not ready: return {"error":"Deployed source did not include the image-loading fix","status":response.status if response else None}
  await page.wait_for_selector(".days .cell.trip",timeout=20000)
  cells=await page.locator(".days .cell.trip").evaluate_all("""els=>els.map((e,i)=>({index:i,text:e.innerText.slice(0,60),computed:getComputedStyle(e).backgroundImage,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))""")
  assets=await page.evaluate("""async()=>{
    const list=Object.values(localTravelPhotos);
    const output=[];
    for(let offset=0;offset<list.length;offset+=12){
      const batch=await Promise.all(list.slice(offset,offset+12).map(src=>new Promise(resolve=>{
        const im=new Image();let done=false;
        const finish=(result)=>{if(done)return;done=true;resolve({src,...result})};
        im.onload=()=>finish({loaded:true,width:im.naturalWidth,height:im.naturalHeight});
        im.onerror=()=>finish({loaded:false,error:'image-error'});
        im.src=src;
        setTimeout(()=>finish({loaded:false,error:'timeout'}),10000);
      })));
      output.push(...batch);
    }
    return output;
  }""")
  await page.locator(".days .cell.trip").nth(2).click()
  await page.wait_for_function("()=>document.querySelectorAll('#tasks img').length>0",timeout=10000)
  await page.wait_for_timeout(1500)
  overlay=await page.evaluate("""()=>({open:document.getElementById('backdrop').classList.contains('open'),photos:[...document.querySelectorAll('#tasks img')].map(e=>({url:e.currentSrc,complete:e.complete,width:e.naturalWidth,display:getComputedStyle(e).display,opacity:getComputedStyle(e).opacity})).slice(0,6)})""")
  return {"status":response.status if response else None,"ready":ready,"cells":cells,"testedImageUrls":len(assets),"imagesLoaded":sum(bool(x.get("loaded")) for x in assets),"failedAssets":[x for x in assets if not x.get("loaded")],"overlay":overlay,"errors":errors,"requestFailures":failed[:20]}

async def main():
  results={}
  async with async_playwright() as p:
    for label,engine,viewport,mobile in [
      ("mobile-webkit","webkit",{"width":390,"height":844},True),
      ("mobile-chromium","chromium",{"width":390,"height":844},True),
      ("desktop-chromium","chromium",{"width":1280,"height":800},False)
    ]:
      browser=None
      try:
        browser=await getattr(p,engine).launch(headless=True)
        page=await browser.new_page(viewport=viewport,device_scale_factor=2 if mobile else 1,is_mobile=mobile,has_touch=mobile)
        results[label]=await inspect(page,label)
      except Exception as e:results[label]={"error":str(e)}
      finally:
        if browser:await browser.close()
  dest=pathlib.Path("test-results");dest.mkdir(exist_ok=True)
  (dest/"browser-image-diagnostic.json").write_text(json.dumps({"git_sha":VERSION,"results":results},indent=2))
  print(json.dumps({k:{"status":v.get("status"),"error":v.get("error"),"cells":len(v.get("cells",[])),"image_urls":v.get("testedImageUrls"),"loaded":v.get("imagesLoaded"),"failed":v.get("failedAssets"),"overlay":v.get("overlay"),"errors":v.get("errors")} for k,v in results.items()},indent=2))
if __name__=="__main__":asyncio.run(main())
