import asyncio, json, pathlib
from playwright.async_api import async_playwright

URL="https://europe-vacation-planner-2026.onrender.com/?smoke=1"
async def main():
  results={}
  async with async_playwright() as p:
    browser=await p.chromium.launch(headless=True)
    for label,viewport,is_mobile in [("mobile",{"width":390,"height":844},True),("desktop",{"width":1280,"height":800},False)]:
      page=await browser.new_page(viewport=viewport,device_scale_factor=2 if is_mobile else 1,is_mobile=is_mobile,has_touch=is_mobile)
      errors=[]; failed=[]
      page.on("pageerror",lambda err: errors.append(str(err)))
      page.on("requestfailed",lambda req: failed.append({"url":req.url[:180],"reason":req.failure}))
      try:
        response=await page.goto(URL,wait_until="domcontentloaded",timeout=45000)
        await page.wait_for_selector(".days .cell.trip",timeout=20000)
        await page.wait_for_timeout(1600)
        cal=await page.locator(".days .cell.trip").evaluate_all("""els=>els.map((e,i)=>({index:i,text:e.innerText.slice(0,60),inline:e.style.backgroundImage,computed:getComputedStyle(e).backgroundImage,backgroundSize:getComputedStyle(e).backgroundSize,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))""")
        # Report how native img test behaves alongside CSS background on this browser
        images=await page.evaluate("""async()=>{let urls=[...new Set([...document.querySelectorAll('.cell.trip')].map(e=>{let a=e.style.backgroundImage.match(/url\\(["']?([^"')]+)/);return a?.[1]}).filter(Boolean))];return await Promise.all(urls.slice(0,16).map(u=>new Promise(resolve=>{const im=new Image();im.onload=()=>resolve({url:u,loaded:true,width:im.naturalWidth});im.onerror=()=>resolve({url:u,loaded:false});im.src=u;setTimeout(()=>resolve({url:u,timeout:true}),6000)})))}""")
        first=page.locator(".days .cell.trip").nth(2)
        await first.click()
        await page.wait_for_timeout(1000)
        overlay=await page.evaluate("""()=>({open:document.getElementById('backdrop').classList.contains('open'),photos:[...document.querySelectorAll('#tasks img')].map(e=>({url:e.currentSrc,complete:e.complete,width:e.naturalWidth,display:getComputedStyle(e).display})).slice(0,4)})""")
        results[label]={"status":response.status if response else None,"cells":cal,"nativeLoads":images,"overlay":overlay,"errors":errors,"requestFailures":failed[:12]}
      except Exception as e:
        results[label]={"error":str(e),"errors":errors,"requestFailures":failed[:12]}
      await page.close()
    await browser.close()
  dest=pathlib.Path("test-results");dest.mkdir(exist_ok=True)
  (dest/"browser-image-diagnostic.json").write_text(json.dumps(results,indent=2))
  print(json.dumps({k:{"status":v.get("status"),"error":v.get("error"),"cells":len(v.get("cells",[])),"images":v.get("nativeLoads",[]),"overlay":v.get("overlay"),"errors":v.get("errors")} for k,v in results.items()},indent=2))
if __name__=="__main__":asyncio.run(main())
