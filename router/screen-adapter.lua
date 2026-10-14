-- A virtual VPN card: never adds peers, interfaces, or route_policy rules.
-- The existing authenticated GL.iNet RPC loader remains in charge of access.
local M = {}
local TUNNEL_ID = 919001

function M.wrap(original, read_snapshot, request, now)
    now = now or os.time
    local wrapped = {}
    local function reserved(v)
        if type(v) == 'table' then
            for _, x in pairs(v) do if reserved(x) then return true end end
            return false
        end
        return v == TUNNEL_ID or v == tostring(TUNNEL_ID) or v == 'speedify-screen'
    end
    local function reject(message)
        return {err_code = -32602, err_msg = message}
    end
    for name, fn in pairs(original) do
        if type(fn) == 'function' then
            wrapped[name] = function(p)
                if reserved(p) then return reject('Speedify supports only its on/off control') end
                return fn(p)
            end
        end
    end
    local function display_state()
        local s = read_snapshot() or {}
        local age = now() - (tonumber(s.timestamp) or 0)
        if age < 0 or age > 15 then s = {state = 'UNKNOWN', pending = s.pending} end
        local state = s.state or 'UNKNOWN'
        local enabled = state == 'CONNECTED' or state == 'CONNECTING' or state == 'AUTO_CONNECTING'
        local status = state == 'CONNECTED' and 1 or ((state == 'CONNECTING' or state == 'AUTO_CONNECTING' or state == 'DISCONNECTING') and 2 or 0)
        if s.pending == 'on' or s.pending == 'off' then
            enabled = s.pending == 'on'
            status = 2
        end
        local label = 'Speedify'
        if state == 'UNKNOWN' then label = 'Speedify: unavailable'
        elseif state == 'LOGGED_OUT' then label = 'Speedify: sign in'
        elseif state == 'OVERLIMIT' then label = 'Speedify: limit reached' end
        return enabled, status, label
    end
    wrapped.get_tunnel = function(p)
        if reserved(p) then return reject('Read the VPN list to view Speedify') end
        local result = original.get_tunnel(p)
        if type(result) ~= 'table' or type(result.tunnels) ~= 'table' then return result end
        local enabled = display_state()
        table.insert(result.tunnels, {
            id = 'speedify-screen', tunnel_id = TUNNEL_ID, name = 'Speedify',
            enabled = enabled, killswitch = false,
            from = {type = 'default'},
            to = {type = 'default', manual = true, domain_list = '', domain_list_len = 0},
            -- wireguard is the stock screen's display schema, not a real WG peer.
            via = {type = 'wireguard', via = 'speedify', configs = {{group_id = TUNNEL_ID, id_list = {TUNNEL_ID}}}},
            options = {options_in_used = false, masq = false, local_access = false, service_policy = false}
        })
        return result
    end
    wrapped.get_status = function(p)
        local result = original.get_status(p)
        if type(result) ~= 'table' or type(result.status_list) ~= 'table' then return result end
        local enabled, status, label = display_state()
        table.insert(result.status_list, {
            tunnel_id = TUNNEL_ID, name = 'Speedify', peer_name = label,
            type = 'wireguard', via = 'speedify', group_id = TUNNEL_ID,
            peer_id = TUNNEL_ID, enabled = enabled, status = status,
            rx_bytes = 0, tx_bytes = 0, ipv4 = '', ipv6 = {}, domain = {}, port = 0
        })
        return result
    end
    wrapped.set_tunnel = function(p)
        if type(p) ~= 'table' or tonumber(p.tunnel_id) ~= TUNNEL_ID then
            if reserved(p) then return reject('Invalid Speedify request') end
            return original.set_tunnel(p)
        end
        if type(p.enabled) ~= 'boolean' then return reject('enabled must be boolean') end
        for k in pairs(p) do
            if k ~= 'tunnel_id' and k ~= 'enabled' then return reject('Speedify supports only on/off') end
        end
        local ok = request(p.enabled and 'on' or 'off')
        if not ok then return {err_code = -32000, err_msg = 'Speedify control is busy or unavailable'} end
        return {tunnel_id = TUNNEL_ID}
    end
    return wrapped
end

return M
