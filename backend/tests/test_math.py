import numpy as np
import pytest
from backend.app.biomechanics.math import angle, normalize, velocity, smooth, rom, asymmetry


@pytest.mark.parametrize('a,b,c,expected', [([0,0],[1,0],[2,0],180),([0,0],[1,0],[1,1],90),([0,0],[1,0],[0,0],0),([1,0],[0,0],[.5,np.sqrt(3)/2],60)])
def test_known_angles(a,b,c,expected):
    assert angle(a,b,c) == pytest.approx(expected)


def test_missing_and_degenerate_angle():
    assert np.isnan(angle([np.nan,0],[1,0],[2,0]))
    assert np.isnan(angle([0,0],[0,0],[1,0]))


def test_normalization_invariant_to_scale_and_translation():
    p, origin = np.array([[100,150],[140,180]]), np.array([100,100])
    assert np.allclose(normalize(p,origin,40), normalize(p*3+25,origin*3+25,120))
    assert np.isnan(normalize(p,origin,0)).all()


def test_variable_timestamp_velocity():
    t = np.array([0,.05,.11,.18,.24])
    xy = np.column_stack([t*2,t*3])
    assert np.allclose(velocity(xy,t),[2,3])
    with pytest.raises(ValueError):
        velocity([1,2,3],[0,0,1])


def test_derivatives_do_not_bridge_missing_or_temporal_gaps():
    values = [0,1,2,np.nan,100,101,102]
    result = velocity(values,np.arange(7)*.1)
    assert np.isnan(result[3])
    assert np.allclose(result[[0,1,2,4,5,6]],10)
    assert np.isnan(velocity([0,1,20,21],[0,.1,1,1.1])).all()


def test_smoothing_retains_gaps_and_reduces_noise():
    t = np.arange(101)*.02
    noisy = np.sin(np.arange(101)*2)*.1+1
    assert np.std(smooth(noisy,t)) < np.std(noisy)
    noisy[50] = np.nan
    assert np.isnan(smooth(noisy,t)[50])
    assert np.allclose(smooth([0,0,np.nan,100,100],[0,.1,.2,.3,.4],1)[[0,1,3,4]],[0,0,100,100])


def test_rom_and_asymmetry():
    assert rom([30,np.nan,150]) == 120
    assert np.isnan(rom([np.nan]))
    assert asymmetry(100,100)==0
    assert asymmetry(100,50)==pytest.approx(200/3)
    assert asymmetry(50,100)==asymmetry(100,50)
    assert asymmetry(None,100) is None
    assert asymmetry(0,0) is None
