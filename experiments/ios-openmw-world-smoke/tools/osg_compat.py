"""Guard the G4-only serializer spelling alias and complete new OSG inventory."""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SERIALIZER='src/osgWrappers/serializers/osg/BufferIndexBinding.cpp'
TARGETS=('g4-serializers-osg','g4-plugin-dds','g4-plugin-tga','g4-plugin-bmp','g4-plugin-png',
    'g4-plugin-jpeg','g4-plugin-osg','osgAnimation','osgParticle','osgShadow')

def literal(text,name):
    values=re.findall(r'^\s*#\s*define\s+'+name+r'\s+(0x[0-9a-fA-F]+|[0-9]+)\s*$',text,re.M)
    if len(values)!=1 or int(values[0],0)!=0x82e0:raise ValueError('Unexpected ANGLE buffer identifier: '+name)

def verify(source,angle=None):
    lock=json.loads((ROOT/'data/gles-source-lock.json').read_text())
    expected=lock['source_sha256_lf']
    actual={p.relative_to(source).as_posix() for folder in ('osgWrappers/serializers/osg','osgAnimation','osgParticle','osgShadow') for p in (source/'src'/folder).glob('*.cpp')}
    if actual!={n for n in expected if '/osgPlugins/' not in n}:raise ValueError('New OSG source inventory differs')
    for name,want in expected.items():
        if hashlib.sha256((source/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=want:raise ValueError('Pinned G4 OSG source changed: '+name)
    text=(source/SERIALIZER).read_text()
    if text.count('ADD_GLENUM_SERIALIZER( Target,GLenum, GL_BUFFER)')!=1:raise ValueError('Serializer semantic anchor changed')
    report={'verified_sources':len(expected),'osg_revision':lock['osg_revision'],'overlay':'none; source-scoped compile definition only'}
    if angle:
        literal((angle/'include/GLES2/gl2ext.h').read_text(),'GL_BUFFER_KHR')
        literal((angle/'include/GLES3/gl32.h').read_text(),'GL_BUFFER')
        report['alias']={'source':SERIALIZER,'definition':'GL_BUFFER=GL_BUFFER_KHR','numeric_value':'0x82e0'}
    return report

def configured(build):
    import provenance
    commands=json.loads((build/'compile_commands.json').read_text())
    entries=[e for e in commands if any('/'+name+'.dir/' in e.get('output',e.get('command','')).replace('\\','/') for name in TARGETS)]
    expected=set(json.loads((ROOT/'data/gles-source-lock.json').read_text())['source_sha256_lf'])
    paths={name:[e for e in entries if Path(e['file']).as_posix().endswith('/'+name)] for name in expected}
    if len(entries)!=len(expected) or any(len(e)!=1 for e in paths.values()):raise ValueError('Incomplete/duplicate new OSG compilation inventory')
    for entry in entries:
        args=provenance.arguments(entry);aliases=[a for a in args if a.startswith('-DGL_BUFFER=')]
        if Path(entry['file']).as_posix().endswith('/'+SERIALIZER):
            if aliases!=['-DGL_BUFFER=GL_BUFFER_KHR']:raise ValueError('Missing/excess serializer alias')
        elif aliases:raise ValueError('Serializer alias leaked into another source')
    return entries

def compiled(build,entries):
    import provenance,dependency_preflight
    result=[]
    for entry in entries:
        args=provenance.arguments(entry)
        if args.count('-o')!=1:raise ValueError('Missing configured OSG object output')
        obj=Path(entry['directory'])/args[args.index('-o')+1]
        if not obj.is_file() or obj.is_symlink():raise ValueError('Missing compiled OSG object: '+str(obj))
        data=obj.read_bytes();dependency_preflight.device_object(data)
        result.append({'source':entry['file'],'object_sha256':hashlib.sha256(data).hexdigest()})
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--angle',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();result=verify(a.source.resolve(),a.angle.resolve() if a.angle else None)
    text=json.dumps(result,indent=2)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text)
    print(text,end='')
