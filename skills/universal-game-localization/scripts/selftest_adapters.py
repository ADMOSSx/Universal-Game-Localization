#!/usr/bin/env python3
"""Focused synthetic regression tests for the Unity, Unreal and Godot adapters."""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import engine_adapters as A

def write(root:Path,rel:str,data:bytes|str=b"")->None:
    path=root/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(data,encoding="utf-8") if isinstance(data,str) else path.write_bytes(data)

def by_id(report:dict,engine_id:str)->dict:
    found=[item for item in report["detected_engines"] if item["engine_id"]==engine_id]
    assert found, f"missing {engine_id}: {report['detected_engines']}"
    return found[0]

def main()->None:
    with tempfile.TemporaryDirectory(prefix="ugl-adapters-") as temp:
        base=Path(temp)
        unity=base/"unity-il2cpp"
        write(unity,"Game.exe",b"MZ")
        write(unity,"UnityPlayer.dll",b"MZ")
        write(unity,"Game_Data/globalgamemanagers",b"dummy")
        write(unity,"Game_Data/il2cpp_data/Metadata/global-metadata.dat",b"dummy")
        write(unity,"Game_Data/Resources/resources.assets",b"dummy")
        write(unity,"Game_Data/StreamingAssets/Localization/en.json",'{"hello":"Hello"}')
        detected=by_id(A.analyze(unity),"unity")
        assert detected["runtime"]=="IL2CPP" and detected["confidence"]=="high",detected
        assert "Game_Data/StreamingAssets/Localization/en.json" in detected["localization_candidates"]
        assert "Game_Data/Resources/resources.assets" in detected["opaque_asset_candidates"]

        mono=base/"unity-mono"
        write(mono,"OldGame.exe",b"MZ")
        write(mono,"UnityPlayer.dll",b"MZ")
        write(mono,"OldGame_Data/Managed/Assembly-CSharp.dll",b"MZ")
        assert by_id(A.analyze(mono),"unity")["runtime"]=="Mono"

        unreal5=base/"unreal5"
        write(unreal5,"Engine/Build/Build.version",json.dumps({"MajorVersion":5,"MinorVersion":3,"PatchVersion":2}))
        write(unreal5,"Game/Content/Paks/Windows/Game.utoc",b"container")
        write(unreal5,"Game/Content/Paks/Windows/Game.ucas",b"container")
        write(unreal5,"Game/Content/Localization/Game/en/Game.locres",b"binary")
        detected=by_id(A.analyze(unreal5),"unreal")
        assert detected["runtime"]=="UE4/UE5" and detected["confidence"]=="high",detected
        assert detected["engine_build_version"]=="5.3.2"
        assert "Game/Content/Localization/Game/en/Game.locres" in detected["localization_candidates"]

        unreal3=base/"unreal3"
        write(unreal3,"System/TJPC.exe",b"MZ")
        write(unreal3,"CookedPC/Maps/Intro.upk",b"UPK")
        write(unreal3,"Localization/INT/Game.int","[Game]\nStart=Start\n")
        detected=by_id(A.analyze(unreal3),"unreal")
        assert detected["runtime"]=="UE3" and detected["engine"]=="Unreal Engine 3",detected

        godot=base/"godot"
        write(godot,"project.godot",'[application]\nconfig/name="Adapter Test"\nconfig/features=PackedStringArray("4.3", "GL Compatibility")\n')
        write(godot,"locale/en.po",'msgid "Hello"\nmsgstr "Hello"\n')
        detected=by_id(A.analyze(godot),"godot")
        assert detected["project_name"]=="Adapter Test" and detected["engine_version_clues"]=="4.3",detected
        assert "locale/en.po" in detected["localization_candidates"]
        assert ".po" not in detected["text_formats_extractable_by_core"]

        godot_pack=base/"godot-pack"
        write(godot_pack,"game.pck",b"GDPC"+b"\x00"*16)
        assert by_id(A.analyze(godot_pack),"godot")["confidence"]=="high"

        generic=base/"generic"
        write(generic,"archives/data.pak",b"not an engine marker")
        assert A.analyze(generic)["primary_engine"]=="UNKNOWN"
        assert not (unity/"ENGINE_ADAPTERS.json").exists()

    print("ENGINE ADAPTERS SELFTEST PASSED")

if __name__=="__main__":
    main()
