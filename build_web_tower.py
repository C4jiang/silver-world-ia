# Silver World animated IA: rebuild the v28 tower as simple stylised geometry for the web page.
# Each level part is re-modelled as its own convex hull (no game meshes, materials or textures are
# shipped); parts are tagged by role (silver / red / dark / glass-outline) and laid out on the v28 spiral.
# Run: python build_web_tower.py <unity_export_dir> <out_dir>   (needs the bpy module, Blender 4.2+)
import bpy, bmesh, math, json, sys, statistics, os
from mathutils import Vector, Matrix

EXP, OUT = sys.argv[1], sys.argv[2]
# v28 render settings (README-render-v4: v14 env + SW_CLEAN, SW_ZERO, SW_A0=174, SW_Z0=27, SW_TOPGAP=7)
K, STEP, A0, R0, GAP, SPH_R, Z0, TOPGAP = 1.6, math.radians(-24), math.radians(174), 15.0, 4.0, 24.0, 27.0, 7.0
ROOMS = ['0-0', '0-1', '0-2', '1-1', '1-3', '1-5', '2-4', '2-5', '3-1', '3-2', '3-3', '3-4', '3-5', '3-6', '3-7', '3-8']
FILES = ['room_m1_level-0-0', 'room00_level-0-1', 'room01_level-0-2', 'room02_level-1-1', 'room03_level-1-3', 'room04_level-1-5',
         'room05_level-2-4', 'room06_level-2-5', 'room07_level-3-1', 'room08_level-3-2', 'room09_level-3-3', 'room10_level-3-4',
         'room11_level-3-5', 'room12_level-3-6', 'room13_level-3-7', None]
LABEL = {'0-0': '0-0', '0-1': '0-1', '0-2': '0-2', '1-1': '1-1', '1-3': '1-2', '1-5': '1-3', '2-4': '2-1', '2-5': '2-2', '3-1': '2-3',
         '3-2': '3-1', '3-3': '3-2', '3-4': '3-3', '3-5': '3-4', '3-6': '3-5', '3-7': '3-6', '3-8': 'END'}

bpy.ops.wm.read_factory_settings(use_empty=True)
coll = bpy.context.scene.collection

def role_of(o, meta):
    comps = meta.get('comps', [])
    mats = [s.material.name.split('.')[0] for s in o.material_slots if s.material]
    if 'Capacitor' in comps: return 'cap'
    if any('Glass' in m for m in mats): return 'glass'
    if any(m in ('m5_Ceramic', 'm4_KineticGate') for m in mats) or 'ElectricalInsulator' in comps: return 'dark'
    if any('Red' in m for m in mats): return 'red'
    if any('Green' in m for m in mats): return 'cap'
    return 'silver'

def islands(o):
    """Split a mesh into its loose pieces, so a U-shaped run of walls does not hull into one solid block."""
    me = o.data; parent = list(range(len(me.vertices)))
    def f(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for e in me.edges:
        a_, b_ = f(e.vertices[0]), f(e.vertices[1])
        if a_ != b_: parent[a_] = b_
    # also weld vertices that sit at the same spot (OBJ splits them per face)
    seen = {}
    for v in me.vertices:
        k = tuple(round(c, 3) for c in v.co)
        if k in seen:
            a_, b_ = f(v.index), f(seen[k])
            if a_ != b_: parent[a_] = b_
        else: seen[k] = v.index
    groups = {}
    for v in me.vertices: groups.setdefault(f(v.index), []).append(o.matrix_world @ v.co)
    return list(groups.values())

def hull_mesh(name, objs):
    """One convex hull per loose piece, merged: each part as a few simple solids."""
    bm = bmesh.new()
    for o in objs:
      for pts in islands(o):
        pb = bmesh.new()
        for v in pts: pb.verts.new(v)
        if len(pb.verts) >= 4:
            try:
                bmesh.ops.convex_hull(pb, input=pb.verts)
                bmesh.ops.dissolve_limit(pb, angle_limit=math.radians(2), verts=pb.verts, edges=pb.edges)
            except Exception:
                pass
        me = bpy.data.meshes.new('tmp'); pb.to_mesh(me); pb.free()
        bm.from_mesh(me); bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); return ob

def hull_pts(name, pts):
    pb = bmesh.new()
    for v in pts: pb.verts.new(v)
    if len(pb.verts) >= 4:
        try:
            bmesh.ops.convex_hull(pb, input=pb.verts)
            bmesh.ops.dissolve_limit(pb, angle_limit=math.radians(2), verts=pb.verts, edges=pb.edges)
        except Exception:
            pass
    me = bpy.data.meshes.new(name); pb.to_mesh(me); pb.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); return ob

layout = []; LEVEL_Z = []
for i, name in enumerate(ROOMS):
    a = A0 + i * STEP; fn = FILES[i]
    parts = {}
    if fn:
        meta = {m['o']: m for m in json.load(open(f'{EXP}/{fn}.json'))}
        before = set(bpy.data.objects)
        bpy.ops.wm.obj_import(filepath=f'{EXP}/{fn}.obj', forward_axis='Y', up_axis='Z')
        objs = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        keep = []
        for o in objs:
            m_ = meta.get(o.name.split('.')[0], {})
            if (m_ and not m_.get('active', True)) or o.dimensions.z > 5.5 or (m_ and 'SilverJourneyRoom' not in m_.get('comps', [])):
                bpy.data.objects.remove(o); continue
            keep.append(o)
        cs = [(o.matrix_world @ (sum((Vector(v) for v in o.bound_box), Vector()) / 8), o) for o in keep]
        mx_ = statistics.median(c.x for c, _ in cs); my_ = statistics.median(c.y for c, _ in cs)
        body = [o for c, o in cs if abs(c.x - mx_) < 9 and abs(c.y - my_) < 9] or keep
        for o in keep:
            if o not in body: bpy.data.objects.remove(o)
        mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
        for o in body:
            for v in o.bound_box:
                w = o.matrix_world @ Vector(v); mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
        Wd = max(mx.x - mn.x, mx.y - mn.y) * K; D = min(mx.x - mn.x, mx.y - mn.y) * K; Hh = (mx.z - mn.z) * K
        long_y = (mx.y - mn.y) > (mx.x - mn.x)
        c = (mn + mx) / 2
        # room-local frame: centred on the footprint, floor at 0, long side along x, scaled by K
        Lm = Matrix.Rotation(-math.pi / 2 if long_y else 0, 4, 'Z') @ Matrix.Scale(K, 4) @ Matrix.Translation((-c.x, -c.y, -mn.z))
        for o in body:
            o.matrix_world = Lm @ o.matrix_world
            r = role_of(o, meta.get(o.name.split('.')[0], {}))
            parts.setdefault(r, []).append(o)
    else:
        Wd, D, Hh = 4.2, 4.2, 2.0
    z = Z0 if i == 0 else LEVEL_Z[-1][1] + GAP
    LEVEL_Z.append((z, z + Hh))
    rad = R0 + D / 2; rot = a + math.pi / 2
    if name == '0-0': rad = R0 + Wd / 2; rot = a + math.pi
    cx, cy = rad * math.cos(a), rad * math.sin(a)
    if name == '3-8': cx = cy = 0.0
    root = bpy.data.objects.new(f'room_{LABEL[name]}', None); coll.objects.link(root)
    root.location = (cx, cy, z); root.rotation_euler = (0, 0, rot)
    caps = []
    for r, objs in parts.items():
        if r == 'cap':  # capacitors stay one mesh each: they turn green one by one
            for k, o in enumerate(objs):
                h = hull_mesh(f'{LABEL[name]}__cap{k}', [o]); h.parent = root
                ctr = sum((Vector(v) for v in h.bound_box), Vector()) / 8; caps.append([round(ctr.x, 2), round(ctr.y, 2), round(ctr.z, 2)])
        else:
            # one mesh per part keeps the explode animation per piece; parts are grouped by role in the name
            for k, o in enumerate(objs):
                for j, pts in enumerate(islands(o)):
                    h = hull_pts(f'{LABEL[name]}__{r}{k}x{j}', pts); h.parent = root
        for o in objs: bpy.data.objects.remove(o)
    print('pieces', LABEL[name], sum(len(islands(o)) for objs in parts.values() for o in objs) if False else '')
    layout.append(dict(id=name, label=LABEL[name], angle=a, rot=rot, pos=[cx, cy, z], h=Hh, w=Wd, d=D, caps=len(caps)))

SPH_Z = LEVEL_Z[-1][1] + TOPGAP + SPH_R
meta = dict(rooms=layout, sphere=dict(z=SPH_Z, r=SPH_R), pole=dict(r=0.9, bottom=-2.6, top=LEVEL_Z[-1][0] + 0.1),
            redcol=dict(bottom=LEVEL_Z[-1][0] + 3.4, top=SPH_Z - SPH_R + 0.6), R0=R0, sea=-2.5)
os.makedirs(OUT, exist_ok=True)
json.dump(meta, open(f'{OUT}/tower.json', 'w'), indent=1)
bpy.ops.export_scene.gltf(filepath=f'{OUT}/tower.glb', export_format='GLB', export_materials='NONE', export_normals=False,
                          export_yup=True, export_draco_mesh_compression_enable=False, export_apply=True)
print('caps total', sum(r['caps'] for r in layout), [(r['label'], r['caps']) for r in layout])
