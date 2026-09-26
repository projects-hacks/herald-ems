"""Where the ambulance is going and when it gets there: the county's receiving hospitals, the vehicle's position,
road drive times from a local router, and matching a spoken destination to the county list."""
from .facilities import Facility, facilities
from .routing import OsrmRouter
from .resolver import DestinationResolver
from .service import TransportService

__all__ = ["Facility", "facilities", "OsrmRouter", "DestinationResolver", "TransportService"]
