extends Node
class_name TcpClient

signal connected
signal disconnected
signal line_received(text: String)
signal error(message: String)

var _peer: StreamPeerTCP
var _is_connected := false
var _buffer := PackedByteArray()

func connect_to_server(host: String, port: int) -> void:
	disconnect_from_server()
	_peer = StreamPeerTCP.new()
	var err := _peer.connect_to_host(host, port)
	if err != OK:
		error.emit("Connect failed: %s" % err)
		return
	_is_connected = true
	connected.emit()

func disconnect_from_server() -> void:
	if _peer:
		_peer.disconnect_from_host()
	_peer = null
	if _is_connected:
		_is_connected = false
		disconnected.emit()

func send_line(text: String) -> void:
	if not _peer or not _is_connected:
		error.emit("Not connected")
		return
	var payload := (text + "\n").to_utf8_buffer()
	var err := _peer.put_data(payload)
	if err != OK:
		error.emit("Send failed: %s" % err)

func _process(_delta: float) -> void:
	if not _peer:
		return
	_peer.poll()
	var status := _peer.get_status()
	if status != StreamPeerTCP.STATUS_CONNECTED:
		if _is_connected:
			disconnect_from_server()
		return

	var bytes := _peer.get_available_bytes()
	if bytes <= 0:
		return

	var data: Array = _peer.get_data(bytes)
	var read_code: int = int(data[0])
	if read_code != OK:
		error.emit("Read failed: %s" % read_code)
		return
	_buffer.append_array(data[1] as PackedByteArray)
	_emit_lines_from_buffer()

func _emit_lines_from_buffer() -> void:
	while true:
		var nl_index := _buffer.find(10) # '\n'
		if nl_index < 0:
			return
		var line_bytes := _buffer.slice(0, nl_index)
		_buffer = _buffer.slice(nl_index + 1)
		var line := line_bytes.get_string_from_utf8().strip_edges()
		if line != "":
			line_received.emit(line)
