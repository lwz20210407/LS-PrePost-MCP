import numpy as np
import pytest

from ls_prepost_mcp.domain.results.curves import CurveError, sae_filter


@pytest.mark.parametrize("cfc", [60, 600])
def test_native_profile_has_independent_chebyshev_reference(cfc):
    signal = pytest.importorskip("scipy.signal")
    t = np.arange(4001)*.00005
    y = 20*np.sin(2*np.pi*5*t)+.5*np.sin(2*np.pi*3000*t)
    got = sae_filter(t,y,cfc,t_unit="s",convention="lsprepost")
    sos = signal.cheby1(2,.25,1.3*cfc,fs=20000,output="sos")
    sos[0,:3] *= 10**(.25/20)  # unit DC gain rather than ripple minimum
    expected = signal.sosfiltfilt(sos,y.astype(np.float32),padlen=0)
    np.testing.assert_allclose(got.y,expected,rtol=0,atol=.001)
    assert got.meta["parameters"]["convention"] == "lsprepost"
    assert got.meta["parameters"]["padding"] == "constant"
    np.testing.assert_array_equal(sae_filter(t,y,cfc,t_unit="s").y,
                                  sae_filter(t,y,cfc,t_unit="s",convention="j211",padding="odd").y)


def test_native_profile_never_silently_ignores_incompatible_padding():
    with pytest.raises(CurveError,match="constant"):
        sae_filter([0,.001,.002],[1,2,3],60,t_unit="s",convention="lsprepost",padding="odd")


def test_native_profile_respects_native_frequency_admission_and_underflow():
    with pytest.raises(CurveError,match="3.3"):
        sae_filter(np.arange(10)*.0001,np.ones(10),3500,t_unit="s",convention="lsprepost")
    with pytest.raises(CurveError,match="underflow"):
        sae_filter(np.arange(10)*.0001,np.full(10,1e-100),60,t_unit="s",convention="lsprepost")


def test_native_profile_is_available_through_curve_ops(tmp_path):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service
    path=tmp_path/"signal.csv"
    path.write_text("time,value\n"+"".join(f"{i*.0001},20\n" for i in range(101)),encoding="utf8")
    r=Service(Settings(tmp_path)).curve_ops([dict(name="a",path=str(path),time_unit="s",value_unit="N")],
        [dict(op="sae_filter",input="a",output="native",cfc=600,convention="lsprepost")])
    assert r["status"] == "succeeded",r.get("error")
    assert r["data"]["steps"][-1]["parameters"]["convention"] == "lsprepost"
