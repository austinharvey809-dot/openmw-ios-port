"""Bounded MW layout diagnostics, NOT the production/genuine Nif::Reader.

Walks records sequentially, checks framing/references and emits metadata only.
Unknown layouts fail rather than searching payloads for type-name substrings.
Never writes original asset bytes, vertex arrays or texture pixels.
"""
import math
import struct


class Cursor:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or size > len(self.data) - self.pos:
            raise ValueError('Truncated NIF layout')
        start = self.pos
        self.pos += size
        return self.data[start:self.pos]

    def read(self, fmt):
        result = struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))
        return result[0] if len(result) == 1 else result

    def count(self, fmt='I'):
        n = self.read(fmt)
        if n > 1000000:
            raise ValueError('Oversized NIF layout count')
        return n

    def string(self):
        return self.take(self.count()).decode('cp1252')

    def refs(self, fmt='I'):
        return [self.read('i') for _ in range(self.count(fmt))]

    def floats(self, n):
        values = struct.unpack('<' + str(n) + 'f', self.take(n * 4))
        if not all(math.isfinite(x) for x in values):
            raise ValueError('Nonfinite NIF layout value')
        return values


def inspect(data):
    c = Cursor(data)
    header = b'NetImmerse File Format, Version 4.0.0.2\n'
    if c.take(len(header)) != header or c.read('I') != 0x04000002:
        raise ValueError('Expected MW 4.0.0.2 layout')
    count = c.count()
    records = []
    for index in range(count):
        record = {'index': index, 'offset': c.pos, 'type': c.string()}
        kind = record['type']
        refs = []
        if kind != 'NiTriShapeData':
            record['name'] = c.string()
            refs.extend((c.read('i'), c.read('i')))  # extra data / controller
        if kind in ('NiNode', 'NiTriShape'):
            record['flags'] = c.read('H')
            transform = c.floats(13)  # translation, rotation, scale
            record['translation'] = transform[:3]
            record['scale'] = transform[-1]
            c.floats(3)  # velocity
            record['properties'] = c.refs()
            refs.extend(record['properties'])
            if c.read('I'):
                raise ValueError('Bounds layout not supported by this diagnostic')
            if kind == 'NiNode':
                record['children'] = c.refs()
                refs.extend(record['children'])
                refs.extend(c.refs())  # effects
            else:
                record['data'], record['skin'] = c.read('ii')
                refs.extend((record['data'], record['skin']))
        elif kind == 'NiTriShapeData':
            vertices = c.count('H')
            positions = c.floats(vertices * 3) if c.read('I') else ()
            normals = bool(c.read('I'))
            normal_values = c.floats(vertices * 3) if normals else ()
            c.floats(4)
            colors = bool(c.read('I'))
            if colors:
                c.floats(vertices * 4)
            uv_sets = c.count('H')
            uv_values = ()
            if c.read('I'):
                uv_values = c.floats(vertices * 2 * uv_sets)
            elif uv_sets:
                raise ValueError('Missing declared UV sets')
            triangles, indices = c.read('H'), c.count()
            values = [c.read('H') for _ in range(indices)]
            if len(positions) != vertices * 3 or indices != 3 * triangles or any(i >= vertices for i in values):
                raise ValueError('Invalid geometry layout')
            degenerate = 0
            for i in range(0, len(values), 3):
                a, b, d = (positions[3*j:3*j+3] for j in values[i:i+3])
                u, v = [b[k]-a[k] for k in range(3)], [d[k]-a[k] for k in range(3)]
                cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                degenerate += sum(x*x for x in cross) == 0
            for i in range(c.count('H')):
                c.take(c.count('H') * 2)  # matching vertex groups
            record.update(vertices=vertices, triangles=triangles, index_count=indices,
                          normals=normals, vertex_colors=colors, uv_sets=uv_sets,
                          degenerate_triangles=degenerate,
                          uv_range=[min(uv_values), max(uv_values)] if uv_values else None)
        elif kind == 'NiTexturingProperty':
            record['flags'], record['apply_mode'] = c.read('HI')
            slots = []
            for slot in range(c.count()):
                item = {'enabled': bool(c.read('I'))}
                if item['enabled']:
                    source, clamp, filtering, uv = c.read('iIII')
                    item.update(source=source, clamp=clamp, filter=filtering, uv_set=uv)
                    refs.append(source)
                    c.take(6)  # legacy PS2/unknown fields, not a texture transform
                    if slot == 5:
                        c.floats(6)
                slots.append(item)
            record['textures'] = slots
        elif kind == 'NiSourceTexture':
            external = bool(c.read('B'))
            record['external'] = external
            if not external:
                raise ValueError('Embedded image not supported by this diagnostic')
            record['file'] = c.string()
            c.take(13)
        elif kind == 'NiMaterialProperty':
            record['flags'] = c.read('H')
            values = c.floats(14)
            record.update(ambient=values[:3], diffuse=values[3:6], specular=values[6:9],
                          emissive=values[9:12], gloss=values[12], alpha=values[13])
        elif kind == 'NiVertexColorProperty':
            record['flags'], record['vertex_mode'], record['lighting_mode'] = c.read('HII')
        elif kind == 'NiAlphaProperty':
            record['flags'], record['threshold'] = c.read('HB')
        elif kind in ('NiZBufferProperty', 'NiSpecularProperty', 'NiShadeProperty', 'NiWireframeProperty', 'NiDitherProperty'):
            record['flags'] = c.read('H')
        elif kind == 'NiStencilProperty':
            values = c.read('HB7I')
            record.update(flags=values[0], enabled=bool(values[1]), draw_mode=values[-1])
        else:
            raise ValueError('Unsupported diagnostic layout: ' + kind)
        record['references'] = refs
        records.append(record)
    roots = c.refs()
    if c.pos != len(data):
        raise ValueError('Trailing NIF layout bytes')
    if any(ref < -1 or ref >= count for r in records for ref in r['references']) or any(r < 0 or r >= count for r in roots):
        raise ValueError('Out-of-range NIF layout reference')
    return {'records': records, 'roots': roots, 'record_count': count,
            'diagnostic_only': True, 'complete_byte_consumption': True}
