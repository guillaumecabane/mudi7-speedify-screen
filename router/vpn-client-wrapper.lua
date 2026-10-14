local json = require('cjson')
local nixio = require('nixio')
local original = assert(loadfile('/usr/lib/speedify-screen/vpn-client.original'))()
local adapter = dofile('/usr/lib/speedify-screen/screen-adapter.lua')
local base = '/var/run/speedify-screen/'

local function read_json(path)
    local f = io.open(path, 'r')
    if not f then return nil end
    local raw = f:read(8192)
    f:close()
    local ok, value = pcall(json.decode, raw)
    if ok and type(value) == 'table' then return value end
end

local function wake_worker()
    local sock = nixio.socket('unix', 'dgram')
    if not sock then return false end
    sock:setblocking(false)
    local n = sock:sendto('w', base .. 'wake.sock')
    sock:close()
    return n == 1
end

local function screen_awake()
    for _, path in ipairs({'/sys/class/backlight/soc:backlight/bl_power', '/sys/class/backlight/backlight/bl_power'}) do
        local f = io.open(path, 'r')
        if f then
            local value = f:read('*l')
            f:close()
            return value == '0'
        end
    end
    return true
end

local function snapshot()
    local s = read_json(base .. 'state.json')
    if not s then
        if screen_awake() then wake_worker() end
        return nil
    end
    if screen_awake() and os.time() - (tonumber(s.timestamp) or 0) >= 2 then wake_worker() end
    local pending = read_json(base .. 'pending/request.json')
    if pending then
        local age = os.time() - (tonumber(pending.timestamp) or 0)
        if age >= 0 and age <= 35 then s.pending = pending.action end
    end
    return s
end

local function request(action)
    -- No RPC values are interpolated into a shell command.
    if os.execute('umask 077; mkdir /var/run/speedify-screen/pending 2>/dev/null') ~= 0 then return false end
    local f = io.open(base .. 'pending/request.tmp', 'w')
    if not f then os.remove(base .. 'pending'); return false end
    f:write(json.encode({action = action, timestamp = os.time()}))
    f:close()
    if not os.rename(base .. 'pending/request.tmp', base .. 'pending/request.json') then
        os.remove(base .. 'pending/request.tmp')
        os.remove(base .. 'pending')
        return false
    end
    if not wake_worker() then
        os.remove(base .. 'pending/request.json')
        os.remove(base .. 'pending')
        return false
    end
    return true
end

return adapter.wrap(original, snapshot, request)
