extends "res://tests/lib/live_test.gd"
## What the server writes (`[[GREEN]]`, `[[CMD:...]]`, `[[PACE:n]]`, blank lines) becomes what the client shows.
## Pure text in, text out: nothing here needs the game to be open.

const MARKUP = preload("res://scripts/text/server_markup.gd")
const TYPEWRITER = preload("res://scripts/text/typewriter.gd")


func run() -> void:
	var gap := "[font_size=%d]\n[/font_size]" % MARKUP.GAP_FONT_SIZE

	# colour and links
	check("a colour wraps the words it covers", MARKUP.to_bbcode("[[GREEN]]hi[[/]] there") == "[color=#6cff6c]hi[/color] there", MARKUP.to_bbcode("[[GREEN]]hi[[/]] there"))
	check("a link wraps its words in a url", MARKUP.to_bbcode("[[CMD:look goblin]]goblin[[/CMD]]") == "[url=cmd:look goblin]goblin[/url]")
	check("a coloured link keeps both, never crossed", MARKUP.to_bbcode("[[CMD:look a]][[RED]]a[[/]][[/CMD]]") == "[url=cmd:look a][color=#ff6060]a[/color][/url]", MARKUP.to_bbcode("[[CMD:look a]][[RED]]a[[/]][[/CMD]]"))
	check("a square bracket in the text is escaped, not read as a tag", MARKUP.to_bbcode("[friendly] [[RED]]x[[/]]").begins_with("[lb]friendly]"), MARKUP.to_bbcode("[friendly] [[RED]]x[[/]]"))
	check("text with no markup is left alone", MARKUP.to_bbcode("plain words") == "plain words")

	# an apostrophe in a command would end a url's value early and swallow the line
	var target: String = MARKUP.url_target("look commander's seal")
	check("an apostrophe in a link target is encoded", target == "look commander%27s seal", target)
	check("and decodes back to what the player meant", target.uri_decode() == "look commander's seal")
	check("a quote is encoded too", MARKUP.url_target('say "hi"') == "say %22hi%22")
	check("a closing bracket is dropped (it would end the tag)", MARKUP.url_target("look a]b") == "look ab")

	# paced text
	check("a paced passage becomes a pace tag", MARKUP.to_bbcode("[[PACE:70]]slow[[/PACE]]") == "[pace=70]slow[/pace]", MARKUP.to_bbcode("[[PACE:70]]slow[[/PACE]]"))
	var runs: Array = TYPEWRITER.runs_of("fast[pace=40]slow[/pace]fast again")
	check("the typewriter splits text into runs with their speeds", runs == [["fast", 0.0], ["slow", 40.0], ["fast again", 0.0]], str(runs))
	check("pace markers can be stripped for a log that is not typed out", TYPEWRITER.without_pace("a[pace=40]b[/pace]c") == "abc")

	# spacing: one blank line is a small gap, a scene break is four
	check("one blank line between paragraphs is one small gap", MARKUP.tighten("a\n\nb") == "a\n" + gap + "b", JSON.stringify(MARKUP.tighten("a\n\nb")))
	check("two blank lines (a new scene) are four small gaps", MARKUP.tighten("a\n\n\nb") == "a\n" + gap + gap + gap + gap + "b", JSON.stringify(MARKUP.tighten("a\n\n\nb")))
	check("a single newline is left as written", MARKUP.tighten("a\nb") == "a\nb")
	check("one newline at the very start is one small gap", MARKUP.tighten("\nDawn breaks.") == gap + "Dawn breaks.", JSON.stringify(MARKUP.tighten("\nDawn breaks.")))
	check("two at the start are kept as written", MARKUP.tighten("\n\nThe room.") == "\n\nThe room.", JSON.stringify(MARKUP.tighten("\n\nThe room.")))

	# the room pane drops the weather sentence (the world panel shows it)
	var room := "[MISTVALE]\n\nA square.\n\nThe weather is cloudy.\n\nExits: north"
	check("the weather sentence is dropped from a room description", not MARKUP.without_weather_line(room).contains("The weather"), MARKUP.without_weather_line(room))
	check("but kept in the weather command's own answer", MARKUP.without_weather_line("The weather is cloudy.") == "The weather is cloudy.")
