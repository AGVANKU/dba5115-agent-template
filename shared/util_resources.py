from azure.identity import ClientSecretCredential

def get_credential(auth: dict) -> ClientSecretCredential:
    """
    Create and return a ClientSecretCredential using the provided
    service principal credentials.

    Args:
        auth: A dictionary containing 'TenantId', 'ClientId', and 'ClientSecret' (PascalCase).

    Returns:
        ClientSecretCredential: The created credential object.
    """
    return ClientSecretCredential(
        tenant_id=auth["TenantId"],
        client_id=auth["ClientId"],
        client_secret=auth["ClientSecret"]
    )