-- Exact coastal road surfaces attached to InfMap2's existing terrain chunks.
-- World coordinates stay virtual; InfMap2's render matrix localizes the mesh.
return function(data_path, part_count)
    local sections = {}
    for index = 1, part_count do
        local path = data_path .. string.format("part_%04d.lua", index)
        if SERVER then AddCSLuaFile(path) end
        for _, section in ipairs(include(path)) do
            for point = 2, 7 do
                section[point] = Vector(section[point][1], section[point][2], section[point][3])
            end
            sections[#sections + 1] = section
        end
    end
    local collision_buckets, draw_buckets = {}, {}
    local function key(x, y) return x .. ":" .. y end
    local function bucket_add(buckets, x, y, segment)
        local name = key(x, y)
        local bucket = buckets[name]
        if not bucket then
            bucket = {x = x, y = y, segments = {}}
            buckets[name] = bucket
        end
        bucket.segments[#bucket.segments + 1] = segment
    end
    local function each_triangle(segment, callback)
        local a, b = sections[segment], sections[segment + 1]
        for band = 1, 5 do
            local left, right, next_left, next_right = a[band + 1], a[band + 2], b[band + 1], b[band + 2]
            -- Clockwise, matching InfMap2.GenerateChunkVertexMesh.
            callback(left, next_left, right, band, a[1], b[1], a[1], 0, 0, 1)
            callback(next_left, next_right, right, band, b[1], b[1], a[1], 0, 1, 1)
        end
    end
    local installed = false
    local function install()
        if installed then return end
        if not InfMap2 or not InfMap2.GenerateChunkVertexMesh then
            error("gm_inf_island: coastal road requires InfMap2 0.41b terrain support")
        end
        installed = true
        local size = InfMap2.ChunkSize
        local spacing = size / InfMap2.World.Terrain.Samples[1]
        for index = 1, #sections - 1 do
            local a, b = sections[index], sections[index + 1]
            local min_x, min_y, max_x, max_y = math.huge, math.huge, -math.huge, -math.huge
            for _, section in ipairs({a, b}) do
                for point = 2, 7 do
                    local p = section[point]
                    min_x, min_y = math.min(min_x, p.x), math.min(min_y, p.y)
                    max_x, max_y = math.max(max_x, p.x), math.max(max_y, p.y)
                end
            end
            -- Physics chunks overlap by one terrain cell; roads must too.
            for x = math.floor((min_x - spacing) / size + .5), math.floor((max_x + spacing) / size + .5) do
                for y = math.floor((min_y - spacing) / size + .5), math.floor((max_y + spacing) / size + .5) do
                    bucket_add(collision_buckets, x, y, index)
                end
            end
            local x = math.floor((a[4].x + b[4].x) / (2 * size) + .5)
            local y = math.floor((a[4].y + b[4].y) / (2 * size) + .5)
            bucket_add(draw_buckets, x, y, index)
        end
        local terrain_mesh = InfMap2.GenerateChunkVertexMesh
        InfMap2.GenerateChunkVertexMesh = function(megapos, lod, limit_height)
            local vertices = terrain_mesh(megapos, lod, limit_height)
            -- InfMap2 uses false for visual terrain; its collider calls omit it.
            if limit_height == false then return vertices end
            local bucket = collision_buckets[key(megapos.x, megapos.y)]
            if not bucket then return vertices end
            local offset = megapos * size
            for _, segment in ipairs(bucket.segments) do
                each_triangle(segment, function(a, b, c)
                    vertices[#vertices + 1] = a - offset
                    vertices[#vertices + 1] = b - offset
                    vertices[#vertices + 1] = c - offset
                end)
            end
            return vertices
        end
        -- The origin chunk can already have been cached by other addons.
        InfMap2.Cache.OriginChunkMesh = nil
    end
    hook.Add("Initialize", "gm_inf_island_coastal_road", install)
    hook.Add("InitPostEntity", "gm_inf_island_coastal_road", install)

    if SERVER then
        concommand.Add("ih17_road_start", function(player)
            if not IsValid(player) then return end
            local a, b = sections[1], sections[2]
            local position = (a[4] + a[5]) * .5
            local forward = (b[4] + b[5]) * .5 - position
            player:SetPos(position + Vector(0, 0, 72))
            player:SetEyeAngles(forward:Angle())
        end)
        return
    end

    -- Valve's coastline asphalt/gravel textures, with a model-compatible
    -- shader because streamed IMesh geometry has no BSP lightmap coordinates.
    local materials = {
        CreateMaterial("gm_inf_island_coastal_gravel", "VertexLitGeneric", {
            ["$basetexture"] = "nature/gravelfloor004a", ["$vertexcolor"] = "1",
        }),
        CreateMaterial("gm_inf_island_coastal_asphalt", "VertexLitGeneric", {
            ["$basetexture"] = "concrete/concretefloor037b", ["$vertexcolor"] = "1",
        }),
    }
    local cache = {}
    local function destroy(entry)
        for _, batch in ipairs(entry) do batch.mesh:Destroy() end
    end
    local function build(bucket)
        local entry = {}
        for material = 1, 2 do
            local vertices = {}
            local function flush()
                if #vertices == 0 then return end
                local object = Mesh()
                object:BuildFromTriangles(vertices)
                entry[#entry + 1] = {mesh = object, material = material}
                vertices = {}
            end
            for _, segment in ipairs(bucket.segments) do
                each_triangle(segment, function(a, b, c, band, sa, sb, sc, ua, ub, uc)
                    if (band == 3 and 2 or 1) ~= material then return end
                    if #vertices + 3 > 32760 then flush() end
                    local normal = -((b - a):Cross(c - a)):GetNormalized()
                    for _, v in ipairs({{a, sa, ua}, {b, sb, ub}, {c, sc, uc}}) do
                        local u, t = v[3], v[2] / 512
                        if band == 1 or band == 5 then u, t = v[1].x / 512, v[1].y / 512 end
                        vertices[#vertices + 1] = {pos = v[1], normal = normal, u = u, v = t}
                    end
                end)
            end
            flush()
        end
        return entry
    end
    hook.Add("PostDrawOpaqueRenderables", "gm_inf_island_coastal_road", function(depth, skybox)
        if depth or skybox or not installed then return end
        local player = LocalPlayer()
        if not IsValid(player) then return end
        local mega = player:GetMegaPos()
        local radius = InfMap2.Visual.RenderDistance + 1
        -- VertexLitGeneric IMesh draws otherwise inherit the last prop's
        -- lighting. Establish daylight explicitly and clear its local lights.
        render.ResetModelLighting(.7, .7, .7)
        render.SetLocalModelLights()
        for name, bucket in pairs(draw_buckets) do
            local visible = math.abs(bucket.x - mega.x) <= radius and math.abs(bucket.y - mega.y) <= radius
            if visible then
                if not cache[name] then cache[name] = build(bucket) end
                for _, batch in ipairs(cache[name]) do
                    render.SetMaterial(materials[batch.material])
                    batch.mesh:Draw()
                end
            elseif cache[name] then
                destroy(cache[name])
                cache[name] = nil
            end
        end
        render.ResetModelLighting(0, 0, 0)
    end)
    hook.Add("ShutDown", "gm_inf_island_coastal_road", function()
        for _, entry in pairs(cache) do destroy(entry) end
        cache = {}
    end)
end
