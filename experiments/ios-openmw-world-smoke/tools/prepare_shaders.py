"""GLES3 platform adaptation of pinned OpenMW shaders, without upstream writes.

Keep upstream material, lighting, fog and terrain arithmetic. GLES permits only
one shader per stage: inline @link modules after their interface declarations.
The G4 profile has no user clipping planes, shadows, clustered compute, MRT,
multiview, water reflections or postprocessing. Those require separate ports.
"""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
SOURCE=REPO/'files/shaders'
ENTRIES=('objects.vert','objects.frag','terrain.vert','terrain.frag','terrain_composite.vert','terrain_composite.frag')
INCLUDE=re.compile(r'^\s*#include\s+"([^"]+)"\s*$',re.M)
LINK=re.compile(r'^\s*@link\s+"([^"]+)"\s+if\s+([^\n]+)$',re.M)

def key(text):return hashlib.sha256(text.encode()).hexdigest()[:24].upper()

def resolve(name,parent):
    candidates=[SOURCE/name,SOURCE/'compatibility'/name,parent.parent/name]
    for path in candidates:
        if path.is_file() and path.resolve().is_relative_to(SOURCE.resolve()):return path.resolve()
    raise ValueError('Missing upstream shader include: '+name)

def flatten(path,stack,inputs):
    path=path.resolve();relative=path.relative_to(SOURCE.resolve()).as_posix()
    if path in stack:return '' # Interface already being emitted before its linked implementation.
    source=path.read_text(encoding='utf-8');inputs[relative]=hashlib.sha256(source.replace('\r\n','\n').encode()).hexdigest()
    links=LINK.findall(source);source=LINK.sub('',source)
    source=re.sub(r'^\s*#version[^\n]*$','',source,flags=re.M)
    source=INCLUDE.sub(lambda match:flatten(resolve(match[1],path),(*stack,path),inputs),source)
    for name,condition in links:
        source+='\n#if '+condition+'\n'+flatten(resolve(name,path),(*stack,path),inputs)+'\n#endif\n'
    guard='G4_INCLUDE_'+key(relative)
    return '\n#ifndef '+guard+'\n#define '+guard+'\n'+source+'\n#endif\n'

def adapt(source,stage):
    source=re.sub(r'\bvarying\b','out' if stage=='vert' else 'in',source)
    source=re.sub(r'\battribute\b','in',source)
    replacements={'gl_Vertex':'osg_Vertex','gl_Color':'osg_Color','gl_Normal':'osg_Normal',
        'gl_NormalMatrix':'osg_NormalMatrix','gl_ModelViewMatrix':'osg_ModelViewMatrix',
        'gl_ModelViewProjectionMatrix':'osg_ModelViewProjectionMatrix',
        'texture2D':'texture','textureCube':'texture','texture2DLod':'textureLod','textureCubeLod':'textureLod',
        'textureSize2D':'textureSize'}
    for before,after in replacements.items():source=re.sub(r'\b'+before+r'\b',after,source)
    # Preserve the @UV substitutions performed by the genuine ShaderManager.
    source=source.replace('gl_MultiTexCoord','osg_MultiTexCoord')
    # ES3 has no desktop implicit int-to-float arithmetic. Keep the upstream
    # integer truncation, then explicitly convert its result for multiplication.
    source=source.replace('log(abs(viewSpaceZ) / near) * int(gridSize.z)',
                          'log(abs(viewSpaceZ) / near) * float(int(gridSize.z))')
    source=re.sub(r'^\s*gl_ClipVertex\s*=\s*viewPos\s*;','',source,flags=re.M)
    source=re.sub(r'gl_FragData\s*\[\s*0\s*\]','g4_Color',source)
    source=re.sub(r'gl_FragData\s*\[\s*1\s*\]','g4_Normal',source)
    # Desktop separate modules can redeclare identical uniforms. Inline ES3
    # declarations need guards, including declarations inside conditional code.
    def uniform(match):
        text=match[0];guard='G4_UNIFORM_'+key(' '.join(text.split()))
        return '\n#ifndef '+guard+'\n#define '+guard+'\n'+text+'\n#endif\n'
    source=re.sub(r'^\s*uniform\s+[^;{}\n]+;',uniform,source,flags=re.M)
    header='#version 300 es\nprecision highp float;\nprecision highp int;\n'
    if stage=='vert':
        header+='in vec4 osg_Vertex;\nin vec4 osg_Color;\nin vec3 osg_Normal;\n'
        header+='\n'.join('in vec4 osg_MultiTexCoord'+str(i)+';' for i in range(8))+'\n'
        header+='uniform mat4 osg_ModelViewMatrix;\nuniform mat4 osg_ModelViewProjectionMatrix;\nuniform mat3 osg_NormalMatrix;\n'
    else:header+='uniform mat3 osg_NormalMatrix;\nlayout(location=0) out vec4 g4_Color;\nlayout(location=1) out vec4 g4_Normal;\n'
    return header+source

def generate(output):
    output=output.resolve()
    if output.is_relative_to(REPO) and not output.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Generated shaders must be outside sources or under artifacts')
    inputs={};result={}
    for entry in ENTRIES:
        target=output/'compatibility'/entry;target.parent.mkdir(parents=True,exist_ok=True)
        text=adapt(flatten(SOURCE/'compatibility'/entry,(),inputs),entry.rsplit('.',1)[-1])
        target.write_text(text,encoding='utf-8',newline='\n');result[entry]=hashlib.sha256(text.encode()).hexdigest()
    report={'scope':'GLES3 platform adaptation; no GPU acceptance','upstream_sha256_lf':dict(sorted(inputs.items())),
        'generated_sha256':result,'profile':{'multiview':False,'clustered':False,'shadows':False,'user_clip_planes':False,'MRT':False}}
    (output/'shader-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(generate(a.output),indent=2))
