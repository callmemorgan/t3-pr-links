#!/usr/bin/env python3
"""Preview extension screens with sample data; never connects to T3 or SSH."""
import argparse
import json
import shutil
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK = r'''
(() => {
  const listeners = [];
  let preferences = {};
  const threads = [
    {id:"example-1",environmentId:"example-env",title:"Allow pinned dependency sources",computer:"Mac Mini",branch:"codex/dependency-sources",project:"Example project",workspace:"/example/worktrees/dependency-sources",workspaceType:"worktree",updatedAt:"2026-10-12T20:00:00Z",matchType:"repository",pullRequests:[{repository:"example/repository",number:57}]},
    {id:"example-2",environmentId:"example-env",title:"Improve branch discovery",computer:"This computer",branch:"feature/branch-lookup",project:"Example project",workspace:"/example/repository",workspaceType:"project",updatedAt:"2026-10-11T20:00:00Z",matchType:"repository",pullRequests:[]},
    {id:"example-3",environmentId:"example-env",title:"Archived browser integration",computer:"Mac Mini",branch:"feature/browser-links",project:"Example project",archived:true,updatedAt:"2026-09-10T20:00:00Z",matchType:"repository",pullRequests:[{repository:"example/repository",number:42}]}
  ];
  const environments = [{name:"This computer",ok:true},{name:"Mac Mini",ok:true}];
  let config = {userdata:"~/.t3/userdata",sshHosts:[{host:"mac-mini",name:"Mac Mini",userdata:"~/.t3/userdata"}]};
  const limited = new URL(location.href).searchParams.get("limited") === "1";
  const response = {ok:true,threads,environments,...(limited ? {truncated:true,lookupWarnings:["Some matching threads were omitted because the result limit was reached."]} : {})};
  window.chrome = {
    runtime:{getURL:path=>new URL(path,location.href).href,getManifest:()=>({version:PREVIEW_VERSION}),async sendMessage(message){
      if(message.type==="getConfig") return {ok:true,config};
      if(message.type==="saveConfig") {config=message.config;return {ok:true,config};}
      if(message.type==="checkoutLookup") return {ok:true,threads:[{id:message.threadId,environmentId:message.environmentId,checkout:{state:"branch",branch:"codex/dependency-sources",matchesRecorded:true}}]};
      if(message.type==="status") return {ok:true,threadCount:3,environments};
      if(message.type==="lookup") return {...response,threads:[{...threads[0],matchType:"linked"}]};
      if(message.type==="directBranchLookup") return {...response,threads:threads.filter(thread=>thread.branch===message.branch).map(thread=>({...thread,matchType:"branch"}))};
      return response;
    }},
    tabs:{async query(){return [{id:1}];},async sendMessage(){
      if(new URL(location.href).searchParams.get("branch")==="1") return {branch:{repository:"example/repository",branch:"codex/dependency-sources"},result:{...response,threads:[{...threads[0],matchType:"branch"}]}};
      return {pr:{repository:"example/repository",number:57},head:{repository:"example/repository",branch:"codex/dependency-sources"},result:{...response,threads:[{...threads[0],matchType:"linked"}]}};
    }},
    storage:{local:{async get(){return {preferences};},async set(data){preferences=data.preferences;listeners.forEach(fn=>fn({preferences:{newValue:preferences}},"local"));}},onChanged:{addListener(fn){listeners.push(fn);}}}
  };
  document.addEventListener("DOMContentLoaded",()=>{
    const banner=document.createElement("div");banner.textContent="PREVIEW · Sample data · No T3 or SSH connection";
    banner.style.cssText="padding:8px 20px;background:#e8ddfc;color:#43236f;font:600 12px/1.5 sans-serif";
    document.body.prepend(banner);
  });
})();
'''

PR_PAGE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>T3 compact PR panel preview</title><link rel="stylesheet" href="content.css">
<style>body{margin:0;color:#1f2328;background:#fff;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1100px;margin:50px auto;padding:0 24px}h1{font-size:26px;margin:0 0 12px}nav{padding:14px 0;border-bottom:1px solid #d1d9e0}p{color:#59636e}</style></head>
<body><main><div id="partial-discussion-header"><h1>Allow pinned dependency sources <span style="color:#59636e">#57</span></h1>
<p>Example pull request · example/repository</p><nav>Conversation &nbsp;&nbsp; Commits &nbsp;&nbsp; Checks &nbsp;&nbsp; Files changed</nav></div></main>
<script src="preview-mock.js"></script><script src="common.js"></script><script src="ui.js"></script><script src="settings.js"></script>
<script>const realPageContext=T3Pr.pageContext;T3Pr.pageContext=document=>realPageContext(document,"https://github.com/example/repository/pull/57");</script>
<script src="content.js"></script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="t3-pr-preview-") as directory:
        destination = Path(directory)
        shutil.copytree(ROOT / "extension", destination, dirs_exist_ok=True)
        version = json.loads((ROOT / "extension/manifest.json").read_text())["version"]
        (destination / "preview-mock.js").write_text("const PREVIEW_VERSION=" + json.dumps(version) + ";\n" + MOCK)
        (destination / "pr.html").write_text(PR_PAGE)
        for name in ("threads.html", "popup.html", "options.html"):
            page = destination / name
            page.write_text(page.read_text().replace("<script src=\"common.js\">", "<script src=\"preview-mock.js\"></script><script src=\"common.js\">"))
        handler = partial(SimpleHTTPRequestHandler, directory=directory)
        with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            print(f"Sample-data preview: http://127.0.0.1:{args.port}/threads.html?repository=example%2Frepository", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
