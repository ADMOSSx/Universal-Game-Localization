#!/usr/bin/env python3
"""Read-only engine adapter discovery for Unity, Unreal and Godot game folders."""
from __future__ import annotations
import argparse, json, os, re, sys, tempfile
from pathlib import Path
from typing import Iterable

SKIP_DIRS={".git","__pycache__","node_modules",".svn"}
MAX_FILES=250_000
MAX_METADATA_BYTES=256*1024

def _norm(path:str)->str:
    return path.replace("\\","/").strip("/").lower()

def _collect_paths(root:Path)->list[str]:
    paths=[]
    for current,dirs,files in os.walk(root,followlinks=False):
        base=Path(current)
        dirs[:]=[d for d in dirs if d.lower() not in SKIP_DIRS and not (base/d).is_symlink()]
        for name in files:
            item=base/name
            if item.is_symlink(): continue
            paths.append(item.relative_to(root).as_posix())
            if len(paths)>=MAX_FILES: return paths
    return paths

def _read_small_text(path:Path)->str:
    try:
        if path.is_symlink() or path.stat().st_size>MAX_METADATA_BYTES: return ""
        return path.read_text(encoding="utf-8-sig",errors="replace")
    except OSError: return ""

def _unreal_version(root:Path,paths:list[str])->str:
    for rel in paths:
        if not _norm(rel).endswith("engine/build/build.version"): continue
        try:
            data=json.loads(_read_small_text(root/rel))
            major,minor,patch=data.get("MajorVersion"),data.get("MinorVersion"),data.get("PatchVersion")
            if major is not None and minor is not None:
                return f"{major}.{minor}"+(f".{patch}" if patch is not None else "")
        except (ValueError,AttributeError): pass
    return ""

def _unity(root:Path,paths:list[str])->dict|None:
    norm=[_norm(p) for p in paths]
    names={Path(p).name for p in norm}
    has_player="unityplayer.dll" in names
    has_global=bool(names & {"globalgamemanagers","globalgamemanagers.assets"})
    has_resources="resources.assets" in names
    has_gameassembly="gameassembly.dll" in names
    has_metadata=any(Path(p).name=="global-metadata.dat" and "il2cpp_data/metadata/" in p for p in norm)
    has_managed=any("/managed/" in f"/{p}/" for p in norm)
    has_project_version=any(p.endswith("projectsettings/projectversion.txt") for p in norm)
    data_roots=sorted({"/".join(p.split("/")[:i+1]) for p in norm for i,part in enumerate(p.split("/")[:-1]) if part.endswith("_data")})
    evidence=[]
    if has_player: evidence.append("UnityPlayer.dll")
    if has_global: evidence.append("globalgamemanagers")
    if has_resources: evidence.append("resources.assets")
    if has_gameassembly or has_metadata: evidence.append("IL2CPP runtime marker")
    if has_managed: evidence.append("Managed assemblies")
    if has_project_version: evidence.append("ProjectSettings/ProjectVersion.txt")
    if data_roots: evidence.append("*_Data directory")
    if len(evidence)<2: return None
    runtime="IL2CPP" if has_gameassembly or has_metadata else "Mono" if has_managed else "unknown"
    localization=[p for p in paths if any(k in f"/{_norm(p)}/" for k in ("/streamingassets/","/localization/","/localisation/","/resources/","/assets/")) and Path(p).suffix.lower() in {".json",".csv",".tsv",".txt",".xml",".po",".loc",".assets",".bundle"}]
    opaque=[p for p in paths if Path(p).suffix.lower() in {".assets",".bundle",".resource"}]
    return {
      "engine":"Unity","engine_id":"unity","runtime":runtime,
      "confidence":"high" if len(evidence)>=4 else "medium","score":min(100,30+15*len(evidence)),
      "evidence":sorted(set(evidence)),"data_roots":data_roots,
      "localization_candidates":localization[:30],"opaque_asset_candidates":opaque[:30],
      "text_formats_extractable_by_core":[".ini",".int",".properties",".lng",".json",".csv",".tsv",".txt"],
      "next_steps":[
        "Check StreamingAssets and game-specific localization folders first; supported plain-text files can use extract_text.py.",
        "Treat .assets, .bundle and .resource as binary containers; inspect a copy with a compatible Unity tool only after confirming the game/Unity version.",
        "For IL2CPP, do not assume a Mono workflow applies; metadata is a clue, not proof that strings are directly editable.",
        "Run unity_fonts.py only when UnityPy/fontTools are approved and installed; verify Arabic glyphs in-game."
      ],
      "limitations":["Unity asset bundles and serialized assets are not extracted by the core text extractor.","Unity version and serialization format must be established before selecting an external tool."]
    }

def _unreal(root:Path,paths:list[str])->dict|None:
    norm=[_norm(p) for p in paths]
    has_upk=any(p.endswith(".upk") for p in norm)
    has_cookedpc=any("/cookedpc/" in f"/{p}/" for p in norm)
    ue3_loc=[p for p in paths if "/localization/" in f"/{_norm(p)}/" and Path(p).suffix.lower()==".int"]
    has_utoc=any(p.endswith(".utoc") for p in norm)
    has_ucas=any(p.endswith(".ucas") for p in norm)
    has_uasset=any(p.endswith((".uasset",".umap")) for p in norm)
    has_locres=any(p.endswith((".locres",".locmeta")) for p in norm)
    has_engine=any(p.startswith("engine/") for p in norm)
    has_paks=any("/paks/" in f"/{p}/" for p in norm)
    if has_upk or has_cookedpc or ue3_loc:
        generation,runtime="Unreal Engine 3","UE3"
        evidence=[]
        if has_upk: evidence.append(".upk packages")
        if has_cookedpc: evidence.append("CookedPC directory")
        if ue3_loc: evidence.append("Localization/*.int files")
    elif has_utoc or has_ucas or has_uasset or has_locres or (has_paks and has_engine):
        generation,runtime="Unreal Engine 4/5 (generation not proven)","UE4/UE5"
        evidence=[]
        if has_utoc and has_ucas: evidence.append("IoStore pair (.utoc + .ucas)")
        elif has_utoc: evidence.append(".utoc container")
        elif has_ucas: evidence.append(".ucas container")
        if has_uasset: evidence.append(".uasset/.umap packages")
        if has_locres: evidence.append(".locres/.locmeta localization resources")
        if has_paks: evidence.append("Paks directory")
        if has_engine: evidence.append("Engine directory")
    else: return None
    localization=[p for p in paths if Path(p).suffix.lower() in {".locres",".locmeta",".int",".ini",".po",".csv",".tsv",".txt"} and any(k in f"/{_norm(p)}/" for k in ("/localization/","/localisation/","/content/","/config/"))]
    opaque=[p for p in paths if Path(p).suffix.lower() in {".pak",".utoc",".ucas",".uasset",".umap",".upk"}]
    score=min(100,35+16*len(evidence))
    confidence="high" if (has_utoc and has_ucas) or (has_cookedpc and len(evidence)>=2) or len(evidence)>=3 else "medium" if len(evidence)>=2 else "low"
    return {
      "engine":generation,"engine_id":"unreal","runtime":runtime,"confidence":confidence,"score":score,
      "engine_build_version":_unreal_version(root,paths),"evidence":sorted(set(evidence)),
      "localization_candidates":localization[:40],"opaque_asset_candidates":opaque[:40],
      "text_formats_extractable_by_core":[".int",".ini",".properties",".lng",".json",".csv",".tsv",".txt"],
      "next_steps":[
        "Inspect localization resources and language folders before scanning general content.",
        "UE3 .int files may be plain text; UE4/UE5 .locres/.locmeta and package containers are binary and need a compatible parser on copies.",
        "When IoStore (.utoc/.ucas) is present, do not assume a legacy .pak-only workflow works.",
        "Verify engine generation, game build and localization namespace before choosing a tool; ask before installing it."
      ],
      "limitations":["The core extractor does not decode .locres, .pak, .utoc, .ucas, .uasset, .umap or .upk containers.","UE4 versus UE5 cannot be confirmed from package extensions alone."]
    }

def _godot(root:Path,paths:list[str])->dict|None:
    project_files=[p for p in paths if Path(p).name.lower()=="project.godot"]
    pck_paths=[p for p in paths if Path(p).suffix.lower()==".pck"]
    pcks=[]
    for rel in pck_paths:
        try:
            with (root/rel).open("rb") as stream:
                if stream.read(4)==b"GDPC": pcks.append(rel)
        except OSError: pass
    evidence=[]
    if project_files: evidence.append("project.godot project configuration")
    if pcks: evidence.append("Godot PCK magic (GDPC)")
    if not evidence: return None
    project_name,version="",""
    for rel in project_files[:3]:
        raw=_read_small_text(root/rel)
        name_match=re.search(r'(?m)^config/name\s*=\s*"([^"\n]{1,120})"',raw)
        feat_match=re.search(r"(?m)^config/features\s*=\s*(?:\[([^\]]{0,500})\]|PackedStringArray\(([^)]{0,500})\))",raw)
        if name_match and not project_name: project_name=name_match.group(1)
        if feat_match and not version:
            version=", ".join(re.findall(r'"(\d+\.\d+)"',feat_match.group(1) or feat_match.group(2) or ""))
    localization=[p for p in paths if Path(p).suffix.lower() in {".translation",".po",".pot",".csv",".tsv",".json",".tres",".tscn"} and any(k in f"/{_norm(p)}/" for k in ("/locale/","/locales/","/localization/","/localisation/","/translation/","/translations/"))]
    return {
      "engine":"Godot","engine_id":"godot","runtime":"Godot 3/4 (generation not proven)",
      "confidence":"high" if project_files or pcks else "medium","score":min(100,40+25*len(evidence)),
      "project_name":project_name,"engine_version_clues":version,"evidence":sorted(set(evidence)),
      "project_files":project_files[:10],"localization_candidates":localization[:40],"opaque_asset_candidates":pcks[:30],
      "text_formats_extractable_by_core":[".ini",".json",".csv",".tsv",".txt",".po"],
      "next_steps":[
        "For an editable project, inspect project.godot and translation resources; preserve resource UIDs and references.",
        "Prefer source .po/.pot/.csv/.json/.tres/.tscn files when available; translate identified user-facing fields only.",
        "Godot .translation and PCK resources are not plain text; inspect copies with a compatible tool after confirming engine version.",
        "A PCK may be embedded in an exported executable, so absence of a sidecar .pck does not disprove Godot."
      ],
      "limitations":["The core extractor does not unpack .pck or decode Godot .translation resources.","Godot version and whether this is source or exported layout must be established first."]
    }

def analyze(root:Path,paths:Iterable[str]|None=None)->dict:
    root=Path(root).resolve()
    if not root.is_dir(): raise ValueError(f"Not a game folder: {root}")
    file_paths=list(paths) if paths is not None else _collect_paths(root)
    adapters=[x for x in (_unity(root,file_paths),_unreal(root,file_paths),_godot(root,file_paths)) if x]
    adapters.sort(key=lambda item:item["score"],reverse=True)
    return {
      "schema_version":"1.0","game_dir":str(root),"files_scanned":len(file_paths),
      "scan_truncated":len(file_paths)>=MAX_FILES,"detected_engines":adapters,
      "primary_engine":adapters[0]["engine"] if adapters else "UNKNOWN",
      "notes":["Detection is evidence-based and may return more than one candidate.","Candidate paths are leads, not proof that a file contains translatable text.","Opaque assets are never unpacked or modified by this script."]
    }

def main()->int:
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir",help="game or project folder (read-only)")
    parser.add_argument("--out",default="",help="optional JSON report path outside the game folder")
    parser.add_argument("--force",action="store_true",help="replace an existing regular report file")
    args=parser.parse_args()
    root_arg=Path(args.game_dir)
    if root_arg.is_symlink(): raise SystemExit("Refusing to scan through a symbolic-link root.")
    root=root_arg.resolve()
    report=analyze(root)
    rendered=json.dumps(report,ensure_ascii=False,indent=2)
    if args.out:
        output_arg=Path(args.out).absolute()
        if any(p.is_symlink() for p in (output_arg,*output_arg.parents)): raise SystemExit("Refusing an output path with a symbolic-link component.")
        output=output_arg.resolve()
        if output==root or root in output.parents: raise SystemExit("Refusing to write the report inside the game folder.")
        if output.exists() and (not args.force or not output.is_file() or output.is_symlink()):
            raise SystemExit(f"Refusing to replace existing/non-regular output: {output} (use --force for a regular file).")
        output.parent.mkdir(parents=True,exist_ok=True)
        handle=tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",newline="\n",prefix=f".{output.name}.",suffix=".tmp",dir=output.parent,delete=False)
        temp_path=Path(handle.name)
        try:
            with handle: handle.write(rendered+"\n")
            os.replace(temp_path,output)
        finally:
            if temp_path.exists(): temp_path.unlink()
        print(f"Engine adapter report: {output}")
    else: print(rendered)
    if report["detected_engines"]:
        print("Detected: "+", ".join(x["engine"] for x in report["detected_engines"]),file=sys.stderr)
    else:
        print("No Unity, Unreal or Godot adapter matched; keep the generic workflow and research the engine.",file=sys.stderr)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
