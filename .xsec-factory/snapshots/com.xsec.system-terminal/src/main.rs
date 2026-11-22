#[tokio::main]
async fn main() -> anyhow::Result<()> {
    system_terminal_mcp::run_stdio().await
}
