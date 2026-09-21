"""Infrastructure-agnostic, side-effect-free utilities shared across modules.

Per docs/04_Data/Project_Structure.md's "The shared/ Risk": nothing here may
reference a domain concept (Analysis, Finding, Policy, ...) or any
module-specific logic. If it needs to, it belongs in that module's own
domain/, not here.
"""
