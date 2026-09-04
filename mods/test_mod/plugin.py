def setup(api):
    print("Test mod setup called!")
    
    # This should succeed since we have command_registration capability
    @api.register_command(name="mod_hello", category="other", help_text="A mod command.")
    def handle_mod_hello(args, context):
        return "Hello from test_mod!"
        
    # This should fail and raise PermissionError, which PluginManager will catch
    api.broadcast_message("This should fail")
