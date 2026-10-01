# scripts/text/server_markup.gd
#
# The server writes colour and click markup into its text (`engine/config/config_display.py`,
# `engine/utils/text_formatter.py`): `[[CYAN]]` sets the colour, `[[/]]` goes back to the default,
# and `[[CMD:look King Aldous]]...[[/CMD]]` makes the words in between a clickable command. The
# pygame client interpreted it; this turns it into the BBCode a RichTextLabel understands.
#
# Each run of plain text is wrapped on its own (`[url][color]text[/color][/url]`), so a colour
# reset inside a link, or a link closing inside a colour, can never produce crossed tags. Plain
# `[` in the text is escaped, because the server's own text has square brackets in it
# ("[friendly]", "[VARENHOLT - THRONE ROOM]") and RichTextLabel would read them as tags.
#
# Reached through `preload`, not a `class_name`, so it needs no editor class scan.
extends RefCounted

# Server rgb values, brightened where pure blue or red is unreadable on a dark background.
const COLORS := {
	"PURPLE": "#d070ff",
	"RED": "#ff6060",
	"ORANGE": "#ffa540",
	"YELLOW": "#ffe45c",
	"GREEN": "#6cff6c",
	"BLUE": "#6f9bff",
	"DARK_BLUE": "#5577dd",
	"GRAY": "#c0c0c0",
	"BEIGE": "#f5deb3",
	"STEEL_BLUE": "#add8e6",
	"CYAN": "#5ce6e6",
	"WHITE": "#ffffff",
}

# A blank line takes the height of the text on it, so the gap is made by shrinking the newline
# that ends it. Smaller is tighter; 6 is roughly a quarter of a line.
const GAP_FONT_SIZE := 6

static var _token_pattern: RegEx
static var _weather_pattern: RegEx
static var _blank_lines: RegEx


## A room description carries "The weather is cloudy." The world panel shows the weather, so the
## sentence is dropped from a room description (a text with an "Exits:" line). The `weather`
## command's own answer is left alone.
static func without_weather_line(text: String) -> String:
	if text.find("Exits:") == -1 or text.find("The weather is") == -1:
		return text
	if _weather_pattern == null:
		_weather_pattern = RegEx.new()
		_weather_pattern.compile("\n*The weather is [^\n]*")
	return _weather_pattern.sub(text, "", true)


## Blank lines are as tall as a line of text, which reads as double spacing. A run of them
## becomes one short gap, so paragraphs stay apart without the page looking sparse.
static func tighten(bbcode: String) -> String:
	# Blank lines the server put at the very start are deliberate separation, so they are kept.
	var lead := ""
	while bbcode.begins_with("\n"):
		lead += "\n"
		bbcode = bbcode.substr(1)
	if bbcode.find("\n\n") == -1:
		return lead + bbcode
	if _blank_lines == null:
		_blank_lines = RegEx.new()
		_blank_lines.compile("\n{2,}")
	return lead + _blank_lines.sub(bbcode, "\n[font_size=%d]\n[/font_size]" % GAP_FONT_SIZE, true)


static func to_bbcode(text: String) -> String:
	if text.find("[") == -1:
		return text
	if _token_pattern == null:
		_token_pattern = RegEx.new()
		_token_pattern.compile("\\[\\[(/CMD|/|CMD:[^\\]]*|[A-Z_]+)\\]\\]")
	var out := ""
	var color := ""
	var command := ""
	var position := 0
	for found in _token_pattern.search_all(text):
		out += _wrap(text.substr(position, found.get_start() - position), color, command)
		position = found.get_end()
		var token: String = found.get_string(1)
		if token == "/":
			color = ""
		elif token == "/CMD":
			command = ""
		elif token.begins_with("CMD:"):
			command = token.substr(4)
		elif COLORS.has(token):
			color = COLORS[token]
		else:
			out += _wrap(found.get_string(), color, command)   # not a token we know: show it as written
	out += _wrap(text.substr(position), color, command)
	return out


static func _wrap(segment: String, color: String, command: String) -> String:
	if segment == "":
		return ""
	var wrapped := segment.replace("[", "[lb]")
	if color != "":
		wrapped = "[color=%s]%s[/color]" % [color, wrapped]
	if command != "":
		wrapped = "[url=cmd:%s]%s[/url]" % [command.replace("]", ""), wrapped]
	return wrapped
