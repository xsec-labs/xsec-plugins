use anyhow::{Context, Result};
use reqwest::Client;
use serde::Deserialize;
use serde_json::{json, Value};

pub const CONTEXT_METHOD: &str = "xsec.terminal.context";

#[derive(Clone)]
pub struct HostClient {
    endpoint: String,
    client: Client,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HostContext {
    pub session_id: String,
    pub role: String,
    pub artifact_sha256: Option<String>,
    pub capability_hash: Option<String>,
    pub allowed_tools: Vec<String>,
}

#[derive(Deserialize)]
struct HostRpcResponse<T> {
    result: Option<T>,
    error: Option<HostRpcError>,
}

#[derive(Deserialize)]
struct HostRpcError {
    message: String,
}

impl HostClient {
    pub fn new(endpoint: String) -> Result<Self> {
        validate_endpoint(&endpoint)?;
        Ok(Self {
            endpoint,
            client: Client::builder().build()?,
        })
    }

    pub async fn context(&self, handle: &str, tool: &str) -> Result<HostContext> {
        let context: HostContext = self.request(handle, CONTEXT_METHOD, Value::Null).await?;
        context.validate(tool)?;
        Ok(context)
    }

    pub async fn call(&self, handle: &str, method: &str, params: Value) -> Result<Value> {
        self.request(handle, method, params).await
    }

    async fn request<T: for<'de> Deserialize<'de>>(
        &self,
        handle: &str,
        method: &str,
        params: Value,
    ) -> Result<T> {
        if handle.trim().is_empty() {
            anyhow::bail!("system-terminal MCP requires a context handle");
        }
        let response = self
            .client
            .post(&self.endpoint)
            .bearer_auth(handle)
            .json(&json!({
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
            }))
            .send()
            .await
            .context("request system-terminal Host RPC")?;
        let status = response.status();
        let payload: HostRpcResponse<T> = response
            .json()
            .await
            .context("parse system-terminal Host RPC")?;
        if !status.is_success() {
            anyhow::bail!("system-terminal Host RPC request failed with {status}");
        }
        if let Some(error) = payload.error {
            anyhow::bail!("system-terminal Host RPC rejected: {}", error.message);
        }
        payload
            .result
            .context("system-terminal Host RPC returned no result")
    }
}

impl HostContext {
    fn validate(&self, tool: &str) -> Result<()> {
        if self.session_id.is_empty()
            || !matches!(self.role.as_str(), "parent" | "sub")
            || !self
                .artifact_sha256
                .as_deref()
                .is_some_and(|value| !value.is_empty())
            || !self
                .capability_hash
                .as_deref()
                .is_some_and(|value| !value.is_empty())
        {
            anyhow::bail!("system-terminal Host RPC context is incomplete");
        }
        if tool != CONTEXT_METHOD && !self.allowed_tools.iter().any(|allowed| allowed == tool) {
            anyhow::bail!("system-terminal MCP tool is not in the frozen allowlist");
        }
        Ok(())
    }
}

fn validate_endpoint(value: &str) -> Result<()> {
    let endpoint = url::Url::parse(value).context("parse system-terminal Host RPC endpoint")?;
    let valid = endpoint.scheme() == "http"
        && endpoint.host_str() == Some("127.0.0.1")
        && endpoint.port().is_some_and(|port| port != 0)
        && endpoint.path() == "/plugin-host-rpc"
        && endpoint.query().is_none()
        && endpoint.fragment().is_none()
        && endpoint.username().is_empty()
        && endpoint.password().is_none();
    if !valid {
        anyhow::bail!("system-terminal Host RPC endpoint must be the local /plugin-host-rpc route");
    }
    Ok(())
}
