"""Run generated road delivery, collision and rendering code under real Lua."""
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.island_builder import write_addon
from test_coastal_road import coastal_mesh


@unittest.skipUnless(shutil.which("texlua"), "texlua required for Lua execution tests")
class RoadLuaTests(unittest.TestCase):
    def test_server_client_road_mesh_and_chunk_coordinates(self):
        with tempfile.TemporaryDirectory() as temp:
            output = write_addon(coastal_mesh(), Path(temp) / "addon", world_width=49152,
                                 grid_step=1024, max_height=6000, coastal_road=True)
            road = json.loads((output / "lua/infmap2/gm_inf_island/road.json").read_text())
            point = road["sections"][0][2]
            mega = [math.floor(point[0] / 20000 + .5), math.floor(point[1] / 20000 + .5), 1]
            script = Path(temp) / "road-check.lua"
            script.write_text("local root = " + json.dumps(str(output / "lua")) + "\n"
                + "local expected = " + "{" + ",".join(map(str, point)) + "}\n"
                + "local mega = " + "{" + ",".join(map(str, mega)) + "}\n" + r'''
local mt = {}; mt.__index = mt
function Vector(x,y,z) return setmetatable({x=x or 0,y=y or 0,z=z or 0},mt) end
function mt.__add(a,b) return Vector(a.x+b.x,a.y+b.y,a.z+b.z) end
function mt.__sub(a,b) return Vector(a.x-b.x,a.y-b.y,a.z-b.z) end
function mt.__unm(a) return Vector(-a.x,-a.y,-a.z) end
function mt.__mul(a,b) return Vector(a.x*b,a.y*b,a.z*b) end
function mt:Cross(b) return Vector(self.y*b.z-self.z*b.y,self.z*b.x-self.x*b.z,self.x*b.y-self.y*b.x) end
function mt:GetNormalized() local l=math.sqrt(self.x^2+self.y^2+self.z^2); return self*(1/l) end
function mt:Angle() return {} end
function Color(...) return {...} end
local hooks, sent, commands = {}, {}, {}
hook = {Add=function(event,id,f) hooks[event]=hooks[event] or {};hooks[event][id]=f end}
local function run(event,...) for _,f in pairs(hooks[event] or {}) do f(...) end end
function AddCSLuaFile(path) sent[path]=true end
function include(path)
    if CLIENT then assert(sent[path], 'unsent client Lua: '..path) end
    return assert(loadfile(root..'/'..path))()
end
concommand={Add=function(name,f) commands[name]=f end}
timer={Simple=function(delay,f) f() end}
local function base() return {Vector(0,0,-100),Vector(0,1,-100),Vector(1,0,-100)} end
InfMap2={GenerateChunkVertexMesh=base,ChunkSize=20000,Visual={RenderDistance=2},Cache={}}
SERVER=true;CLIENT=false
local config=assert(loadfile(root..'/infmap2/gm_inf_island/main.lua'))()
InfMap2.World={Terrain={Samples=config.world.terrain.samples}}
run('Initialize');run('InitPostEntity') -- must not wrap twice
local chunk=Vector(mega[1],mega[2],mega[3])
local collider=InfMap2.GenerateChunkVertexMesh(chunk,1)
assert(#collider>3 and #collider%3==0,'missing exact road collider triangles')
assert(collider[1].z==-100,'base terrain collider was overwritten')
assert(#InfMap2.GenerateChunkVertexMesh(chunk,1,false)==3,'road must not enter grass-render mesh')
assert(#InfMap2.GenerateChunkVertexMesh(Vector(100,100,0),1)==3,'road leaked to distant chunk')
local found=false
for _,v in ipairs(collider) do
 if math.abs(v.x+mega[1]*20000-expected[1])<.001 and
    math.abs(v.y+mega[2]*20000-expected[2])<.001 and
    math.abs(v.z+mega[3]*20000-expected[3])<.001 then found=true end
end
assert(found,'road collision has wrong virtual XY/Z offset')
local server_count=#collider
local material_params={}
function Material(path) return path end
function CreateMaterial(name,shader,params) material_params[#material_params+1]=params; return name end
local drawn,destroyed,built=0,0,0
local ambient=nil
local local_lights_cleared=false
function Mesh()
 return {BuildFromTriangles=function(self,triangles)
   assert(#triangles%3==0 and #triangles<32768)
   for _,v in ipairs(triangles) do assert(v.pos and v.normal and v.u and v.v) end
   built=built+1
 end,Draw=function()
   assert(ambient and local_lights_cleared,
          'road inherited the previous vehicle/prop lighting')
   drawn=drawn+1
 end,Destroy=function() destroyed=destroyed+1 end}
end
render={SetMaterial=function() end,
 ResetModelLighting=function(r,g,b) ambient=(r>0 and g>0 and b>0) end,
 SetLocalModelLights=function() local_lights_cleared=true end}
local player={GetMegaPos=function() return Vector(mega[1],mega[2],0) end}
function LocalPlayer() return player end
function IsValid(x) return x~=nil end
local spawn={SetPos=function(self,p) self.position=p end, SetEyeAngles=function(self,a) self.angles=a end}
commands.ih17_road_start(spawn)
assert(math.abs(spawn.position.z-expected[3]-72)<.001 and spawn.angles,'road start command failed')
SERVER=false;CLIENT=true;hooks={}
InfMap2.GenerateChunkVertexMesh=base
config=assert(loadfile(root..'/infmap2/gm_inf_island/main.lua'))()
run('Initialize');run('InitPostEntity')
assert(#InfMap2.GenerateChunkVertexMesh(chunk,1)==server_count,'client road collider differs')
run('PostDrawOpaqueRenderables',true,false)
run('PostDrawOpaqueRenderables',false,true)
assert(drawn==0,'road drawn in depth/sky pass')
run('PostDrawOpaqueRenderables',false,false)
assert(drawn>0 and built>0,'road was never drawn')
assert(not ambient,'road lighting leaked to other draws')
assert(material_params[1]['$basetexture']=='nature/gravelfloor004a')
assert(material_params[2]['$basetexture']=='concrete/concretefloor037b')
player.GetMegaPos=function() return Vector(100,100,0) end
local before=drawn
run('PostDrawOpaqueRenderables',false,false)
assert(drawn==before and destroyed==built,'distant road meshes were not freed')
run('ShutDown')
for path in pairs(sent) do
 local f=assert(io.open(root..'/'..path,'rb'));local data=f:read('*a');f:close()
 assert(#data<60000,'oversized client Lua file')
 assert(path==path:lower(),'Linux path capitalization mismatch')
end
''')
            result = subprocess.run([shutil.which("texlua"), str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
