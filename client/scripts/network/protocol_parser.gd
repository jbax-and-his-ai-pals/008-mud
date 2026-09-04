extends Node
class_name ProtocolParser

const CLIENT_PROTOCOL_VERSION := "0.1.0"

func parse_event(line: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(line)
	if typeof(parsed) == TYPE_DICTIONARY:
		return parsed as Dictionary
	return {"type": "raw", "payload": line}

func build_command_envelope(command_text: String, client_capabilities: Dictionary = {}, session_id: String = "client_shell") -> Dictionary:
	var capabilities: Dictionary = {
		"rich_text": true,
		"mobile_variant": false,
		"reduced_motion": false,
		"high_contrast": false,
		"screen_reader_mode": false
	}
	for key in client_capabilities.keys():
		capabilities[key] = client_capabilities[key]

	return {
		"type": "command",
		"session_id": session_id,
		"command_text": command_text,
		"client_capabilities": capabilities,
		"protocol_version": CLIENT_PROTOCOL_VERSION
	}

func build_asset_update_envelope(asset_id: String, base_revision: int, svg_text: String, alt_text: String, session_id: String = "client_shell") -> Dictionary:
	return {
		"type": "asset_update",
		"session_id": session_id,
		"protocol_version": CLIENT_PROTOCOL_VERSION,
		"payload": {
			"asset_id": asset_id,
			"base_revision": base_revision,
			"svg": svg_text,
			"alt_text": alt_text
		}
	}

func build_lock_acquire_envelope(asset_id: String, session_id: String = "client_shell") -> Dictionary:
	return {
		"type": "lock_acquire",
		"session_id": session_id,
		"protocol_version": CLIENT_PROTOCOL_VERSION,
		"payload": {"asset_id": asset_id}
	}

func build_lock_release_envelope(asset_id: String, session_id: String = "client_shell") -> Dictionary:
	return {
		"type": "lock_release",
		"session_id": session_id,
		"protocol_version": CLIENT_PROTOCOL_VERSION,
		"payload": {"asset_id": asset_id}
	}

func build_lock_renew_envelope(asset_id: String, session_id: String = "client_shell") -> Dictionary:
	return {
		"type": "lock_renew",
		"session_id": session_id,
		"protocol_version": CLIENT_PROTOCOL_VERSION,
		"payload": {"asset_id": asset_id}
	}

func build_lock_status_envelope(session_id: String = "client_shell") -> Dictionary:
	return {
		"type": "lock_status",
		"session_id": session_id,
		"protocol_version": CLIENT_PROTOCOL_VERSION
	}

func build_resume_session_envelope(session_id: String) -> Dictionary:
	return {
		"type": "resume_session",
		"session_id": session_id,
		"protocol_version": CLIENT_PROTOCOL_VERSION
	}
