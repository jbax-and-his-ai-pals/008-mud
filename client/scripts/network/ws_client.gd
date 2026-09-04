extends Node
class_name WsClient

signal connected
signal disconnected
signal line_received(text: String)
signal error(message: String)

var _peer: WebSocketPeer
var _is_connected: bool = false

func connect_to_server(host: String, port: int) -> void:
	disconnect_from_server()
	_peer = WebSocketPeer.new()
	var err: int = _peer.connect_to_url("ws://%s:%d" % [host, port])
	if err != OK:
		error.emit("Connect failed: %s" % err)
		return

func disconnect_from_server() -> void:
	if _peer:
		_peer.close()
	_peer = null
	if _is_connected:
		_is_connected = false
		disconnected.emit()

func send_line(text: String) -> void:
	if not _peer or not _is_connected:
		error.emit("Not connected")
		return
	var err: int = _peer.send_text(text)
	if err != OK:
		error.emit("Send failed: %s" % err)

func _process(_delta: float) -> void:
	if not _peer:
		return
	_peer.poll()
	var state: int = _peer.get_ready_state()

	if state == WebSocketPeer.STATE_OPEN:
		if not _is_connected:
			_is_connected = true
			connected.emit()
		_read_all_packets()
		return

	if state == WebSocketPeer.STATE_CLOSING:
		return

	if _is_connected:
		disconnect_from_server()

func _read_all_packets() -> void:
	while _peer.get_available_packet_count() > 0:
		var packet: PackedByteArray = _peer.get_packet()
		var text: String = packet.get_string_from_utf8().strip_edges()
		if text != "":
			line_received.emit(text)
