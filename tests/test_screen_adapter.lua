local adapter = dofile(arg[1] or 'router/screen-adapter.lua')
local original_calls, requests = {}, {}
local state = {state = 'CONNECTED', timestamp = 100}
local function native(name)
    return function(p)
        original_calls[#original_calls+1] = {name = name, params = p}
        return {native = name}
    end
end
local original = {
    get_tunnel = function(p) return {global_enabled = false, tunnels = {{tunnel_id = 10, name = 'Existing'}}, default_tunnels = {}} end,
    get_status = function(p) return {mode = 0, status_list = {{tunnel_id = 10, enabled = false}}} end,
    set_tunnel = native('set_tunnel'),
    remove_tunnel = native('remove_tunnel'),
    order_tunnel = native('order_tunnel'),
    stop = native('stop'),
}
local wrapped = adapter.wrap(original, function() return state end,
    function(action) requests[#requests+1] = action; return true end,
    function() return 100 end)
local tunnels = wrapped.get_tunnel({})
assert(#tunnels.tunnels == 2 and tunnels.tunnels[1].tunnel_id == 10)
assert(tunnels.global_enabled == false and #tunnels.default_tunnels == 0)
assert(tunnels.tunnels[2].name == 'Speedify' and tunnels.tunnels[2].enabled)
local status = wrapped.get_status({})
assert(status.mode == 0 and #status.status_list == 2)
assert(status.status_list[2].status == 1 and status.status_list[2].enabled)

for _,case in ipairs({
    {'LOGGED_IN', false, 0}, {'CONNECTED', true, 1},
    {'CONNECTING', true, 2}, {'AUTO_CONNECTING', true, 2},
    {'DISCONNECTING', false, 2}, {'UNKNOWN', false, 0},
    {'LOGGED_OUT', false, 0}, {'OVERLIMIT', false, 0}
}) do
    state = {state = case[1], timestamp = 100}
    local row = wrapped.get_status({}).status_list[2]
    assert(row.enabled == case[2] and row.status == case[3], case[1])
end
state = {state = 'CONNECTED', timestamp = 80}
assert(not wrapped.get_status({}).status_list[2].enabled, 'stale cache must not show connected')
state = {state = 'LOGGED_IN', timestamp = 100, pending = 'on'}
assert(wrapped.get_status({}).status_list[2].status == 2)
state = {state = 'CONNECTED', timestamp = 100, pending = 'off'}
assert(not wrapped.get_status({}).status_list[2].enabled)
assert(wrapped.get_status({}).status_list[2].status == 2)

assert(wrapped.set_tunnel({tunnel_id = 919001, enabled = true}).tunnel_id == 919001)
assert(wrapped.set_tunnel({tunnel_id = '919001', enabled = false}).tunnel_id == 919001)
assert(requests[1] == 'on' and requests[2] == 'off' and #original_calls == 0)
assert(wrapped.set_tunnel({tunnel_id = 919001, enabled = 'false'}).err_code)
assert(wrapped.set_tunnel({tunnel_id = 919001, enabled = true, via = {}}).err_code)
assert(#requests == 2)
assert(wrapped.remove_tunnel({tunnel_id = 919001}).err_code)
assert(wrapped.order_tunnel({tunnels = {10, 919001}}).err_code)
assert(#original_calls == 0)
for _,method in ipairs({'set_tunnel', 'remove_tunnel', 'order_tunnel', 'stop'}) do
    local p = {tunnel_id = 10, enabled = false}
    assert(wrapped[method](p).native == method)
    assert(original_calls[#original_calls].params == p)
end
assert(#original_calls == 4)
assert(original.get_status({}).status_list[2] == nil, 'native module must not be modified')
print('screen adapter: all assertions passed')
state = {state = 'CONNECTED', timestamp = 1, pending = 'off'}
assert(wrapped.get_status({}).status_list[2].status == 2, 'pending action must survive an idle stale cache')
assert(not wrapped.get_status({}).status_list[2].enabled)
