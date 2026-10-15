"""Execute generated Lua in a server/client harness; texlua is optional."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.island_builder import write_addon

TEXLUA = shutil.which('texlua')

@unittest.skipUnless(TEXLUA, 'texlua required for Lua execution tests')
class LuaRuntimeTests(unittest.TestCase):
    def run_config(self, assertions, grid_step=1000):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mesh = json.loads(Path('tests/fixtures/elaborate-small.json').read_text())
            output = write_addon(mesh, root / 'addon', world_width=20000, grid_step=grid_step,
                                 max_height=20, sea_floor=-100, padding_cells=1)
            script = root / 'check.lua'
            script.write_text('local root = ' + json.dumps(str(output / 'lua')) + '\n' + r'''
local sent = {}
SERVER = true; CLIENT = false
function AddCSLuaFile(path) sent[path] = true end
function include(path)
    if CLIENT then assert(sent[path], 'client file was not sent: '..path) end
    return assert(loadfile(root..'/'..path))()
end
file = {Read = function(path)
    assert(SERVER, 'client cannot read server-only terrain.bin')
    local f = assert(io.open(root..'/'..path, 'rb'))
    local data = f:read('*a'); f:close(); return data
end}
local server = assert(loadfile(root..'/infmap2/gm_inf_island/main.lua'))()
''' + assertions)
            result = subprocess.run([TEXLUA, str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_explicit_sampling_matches_grid_and_even_chunk_alignment(self):
        self.run_config('''
local n = assert(server.world.terrain.samples, 'missing terrain samples')[1]
assert(n % 2 == 0 and n <= 64)
assert(server.chunksize / n <= 1000, 'terrain is coarser than the exported grid')
''')

    def test_callback_compensates_infmap_doubled_coordinates(self):
        self.run_config('''
assert(server.world.terrain.height_function(20000, 20000) == 20, 'wrong world scale')
''')

    def test_client_loads_only_server_sent_lua_files(self):
        self.run_config('''
SERVER = false; CLIENT = true
function Material(path) return path end
function Color(...) return {...} end
hook = {Add = function() end}
local client = assert(loadfile(root..'/infmap2/gm_inf_island/main.lua'))()
for x=-22000,22000,1000 do
  for y=-22000,22000,1000 do
    assert(server.world.terrain.height_function(x,y) == client.world.terrain.height_function(x,y))
  end
end
local count=0
for path in pairs(sent) do
  count=count+1
  local f=assert(io.open(root..'/'..path,'rb')); local contents=f:read('*a'); f:close()
  assert(#contents < 60000, 'Lua transfer chunk exceeds safe file size')
  assert(path == path:lower(), 'case-sensitive path mismatch')
end
assert(count > 1, 'expected multiple terrain files')
''', grid_step=250)

    def test_dense_grid_uses_bounded_mesh_size(self):
        self.run_config("assert(server.world.terrain.samples[1] == 64)", grid_step=250)
