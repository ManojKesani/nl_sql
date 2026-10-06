"""Provider factories. Imports are lazy so unused providers needn't be installed."""


def _groq(**cfg):
    from langchain_groq import ChatGroq
    return ChatGroq(**cfg)


def _nvidia(**cfg):
    from langchain_nvidia_ai_endpoints import ChatNVIDIA
    return ChatNVIDIA(**cfg)


def _openrouter(**cfg):
    from langchain_openrouter import ChatOpenRouter
    return ChatOpenRouter(**cfg)


PROVIDERS = {"groq": _groq, "nvidia": _nvidia, "openrouter": _openrouter}