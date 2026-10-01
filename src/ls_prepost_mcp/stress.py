"""Tension-positive symmetric Cauchy stress; no layer or spatial averaging."""
import math

CONVENTIONS = {
    "components": ["xx", "yy", "zz", "xy", "yz", "xz"],
    "sign": "tension positive; shear entries are tensor components",
    "mean_stress": "trace(sigma)/3",
    "pressure": "-mean_stress (compression positive)",
    "von_mises": "sqrt(3*J2); J2=s:s/2; s=sigma-mean_stress*I",
    "triaxiality": "mean_stress/von_mises (uniaxial tension +1/3)",
    "lode_cos3theta": "(3*sqrt(3)/2)*J3/J2**1.5; J3=det(s)",
    "lode_angle_rad": "acos(lode_cos3theta)/3, range [0,pi/3]",
    "lode_angle_parameter": "1-6*lode_angle_rad/pi; uniaxial tension +1, compression -1",
    "lode_parameter": "(2*sigma2-sigma1-sigma3)/(sigma1-sigma3); principal sigma1>=sigma2>=sigma3; tension -1",
    "undefined": "triaxiality and Lode quantities are null when deviatoric stress is below relative tolerance",
}
NULLABLE = {"triaxiality", "lode_cos3theta", "lode_angle_rad", "lode_angle_deg",
            "lode_angle_parameter", "lode_parameter"}


def native_mises_matches(components, derived, native):
    """Compare native float32-result invariants without an absolute unit-dependent floor."""
    if not math.isfinite(native) or native < 0:
        return False
    scale = max(abs(float(value)) for value in components)
    # Accommodate component rounding near hydrostatic stress; remain invariant
    # under changing stress units. A zero tensor must have exactly zero Mises.
    tolerance = scale * 8 * 2**-23
    return math.isclose(derived, native, rel_tol=2e-4, abs_tol=tolerance)


def stress_metrics(components, relative_tolerance=1e-12):
    import numpy as np
    a = np.asarray(components, dtype=float)
    if a.shape != (6,) or not np.isfinite(a).all():
        raise ValueError("Stress requires six finite values ordered xx,yy,zz,xy,yz,xz")
    if not math.isfinite(relative_tolerance) or not 0 <= relative_tolerance < 1:
        raise ValueError("relative_tolerance must be in [0,1)")
    scale = float(np.max(np.abs(a))) or 1.0
    xx, yy, zz, xy, yz, xz = a / scale
    tensor = np.array([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]])
    mean = float(np.trace(tensor) / 3)
    dev = tensor - mean * np.eye(3)
    j2 = float(np.sum(dev * dev) / 2)
    j3 = float(np.linalg.det(dev))
    mises = math.sqrt(3 * j2)
    p1, p2, p3 = np.linalg.eigvalsh(tensor)[::-1]
    defined = mises > relative_tolerance
    result = dict(zip(CONVENTIONS["components"], map(float, a)))
    result.update(principal_1=float(p1*scale), principal_2=float(p2*scale), principal_3=float(p3*scale),
                  mean_stress=mean*scale, pressure=-mean*scale, von_mises=mises*scale,
                  max_shear=float((p1-p3)*scale/2), j2=j2*scale**2, j3=j3*scale**3,
                  deviatoric_defined=int(defined))
    result.update({key: None for key in sorted(NULLABLE)})
    if defined:
        xi = max(-1.0, min(1.0, 3*math.sqrt(3)/2*j3/j2**1.5))
        theta = math.acos(xi)/3
        result.update(triaxiality=mean/mises, lode_cos3theta=xi, lode_angle_rad=theta,
                      lode_angle_deg=math.degrees(theta), lode_angle_parameter=1-6*theta/math.pi,
                      lode_parameter=float((2*p2-p1-p3)/(p1-p3)))
    if any(v is not None and not math.isfinite(v) for v in result.values()):
        raise ValueError("Stress invariant exceeds floating-point range")
    return result
