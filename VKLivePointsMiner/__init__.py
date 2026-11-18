"""VK Live Points Miner"""

__version__ = "0.1.0"
__author__ = "VK Live Miner Team"

# Lazy imports to avoid missing dependencies on import
__all__ = ['VKLiveMiner', 'VKAuth', 'VKApi', 'VKWebSocket']


def __getattr__(name):
    if name == 'VKLiveMiner':
        from .VKLiveMiner import VKLiveMiner
        return VKLiveMiner
    elif name == 'VKAuth':
        from .classes.VKAuth import VKAuth
        return VKAuth
    elif name == 'VKApi':
        from .classes.VKApi import VKApi
        return VKApi
    elif name == 'VKWebSocket':
        from .classes.VKWebSocket import VKWebSocket
        return VKWebSocket
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
