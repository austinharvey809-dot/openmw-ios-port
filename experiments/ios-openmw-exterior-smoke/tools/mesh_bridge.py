"""Bounded migration seam. Reuse locked G2 conversion; use real SceneUtil::Material.

Generated copies stay in the build directory. No upstream/completed source edits.
This seam is not a replacement for eventual Resource::SceneManager/NifOsg::Loader.
"""
import importlib.util,json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from paths import ROOT,REPO,verify
def generate(output):
    verify();spec=importlib.util.spec_from_file_location('_g3_g2_mesh_bridge',ROOT.parent/'ios-openmw-interior-smoke/tools/bridge.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.generate(output)
    code=(output/'MeshBridge.cpp').read_text()
    def change(old,new):
        nonlocal code
        if code.count(old)!=1:raise ValueError('G3 material bridge anchor differs: '+old[:60])
        code=code.replace(old,new)
    change('#include "Interior.hpp"','#include "Exterior.hpp"\n#include "Material.hpp"')
    change('namespace G2 {','namespace G3 {\nusing Model=G2::Model;using Resources=G2::Resources;')
    change('using G1D::inheritProperty;using G1D::diffuseColor;','')
    change('inheritProperty(material,p.empty()?nullptr:p.getPtr(),context);','G3::inheritProperty(material,p.empty()?nullptr:p.getPtr(),context);')
    change('const auto diffuse=diffuseColor(material,!data->mColors.empty(),context);','const auto diffuse=osg::Vec4(1,1,1,1);')
    change('const bool useColors=!material.vertex||material.vertex->mVertexMode==Nif::NiVertexColorProperty::VertexMode::VertMode_SrcAmbDif;','const bool useColors=true; // Actual SceneUtil::Material determines how the array is consumed.')
    change('applyStaticState(*state,material,det);','applyStaticState(*state,material,det);G3::applyMaterial(*state,material,!data->mColors.empty(),context);')
    (output/'WorldMesh.cpp').write_text(code,encoding='utf-8',newline='\n')
    parts=[]
    for name in ('struct.glsl','colormodes.glsl','vertexcolors.glsl'):
        text=(REPO/'files/shaders/lib/material'/name).read_text()
        text='\n'.join(line for line in text.splitlines() if not line.startswith('#include '))
        parts.append(text)
    (output/'MaterialShader.hpp').write_text('#pragma once\nnamespace G3Shader {inline constexpr char Material[]=R"G3('+ '\n'.join(parts)+')G3";}\n',encoding='utf-8',newline='\n')
    return {'world_mesh_sha256':hashlib.sha256(code.encode()).hexdigest(),'material_source':'unchanged components/sceneutil/material.cpp and upstream material GLSL'}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(generate(a.output)))
