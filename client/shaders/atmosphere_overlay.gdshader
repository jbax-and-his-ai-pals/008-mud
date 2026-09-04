shader_type canvas_item;

uniform vec4 overlay_tint : source_color = vec4(0.0, 0.0, 0.0, 0.0);
uniform float effect_strength : hint_range(0.0, 1.0) = 0.0;

void fragment() {
	float grain = fract(sin(dot(SCREEN_UV * vec2(123.4, 456.7), vec2(12.9898, 78.233))) * 43758.5453);
	float flicker = mix(-0.04, 0.04, grain) * effect_strength;
	vec4 tint = overlay_tint;
	tint.a = clamp(tint.a + flicker, 0.0, 1.0);
	COLOR = tint;
}
