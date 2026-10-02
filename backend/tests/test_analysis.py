import copy
import json
import numpy as np
import pytest
from backend.app.movement_analysis.analyze import analyze
from backend.app.report.build import build_report


def synthetic(width=1000,height=1000):
    frames=[]
    for i in range(91):
        theta=np.deg2rad(90 * i / 90)
        coords={'nose':(500,120),'left_hip':(400,750),'right_hip':(600,750)}
        for side,x,sign in [('left',400,-1),('right',600,1)]:
            s=np.array([x,300]); vector=np.array([sign*np.sin(theta),np.cos(theta)])*180
            coords.update({f'{side}_shoulder':s, f'{side}_elbow':s+vector, f'{side}_wrist':s+2*vector})
        frames.append({'timestamp':i/30,'people':1,'landmarks':{k:{'x':float(p[0])/width,'y':float(p[1])/height,'z':0,'confidence':.99,'visibility':.99,'presence':.99,'timestamp':i/30} for k,p in coords.items()}})
    return frames


def test_synthetic_straight_elbow_and_raise():
    result=analyze(synthetic(),1000,1000)
    for side in ('left','right'):
        arm=result['metrics'][f'{side}_arm']
        assert arm['elbow_min']['value']==pytest.approx(180,abs=1e-5)
        assert arm['shoulder_max']['value']==pytest.approx(89,abs=.1)
        assert arm['time_to_max']['value']==3
    assert result['asymmetry']['shoulder_rom']['index_percent']==pytest.approx(0,abs=1e-5)
    assert result['metrics']['trunk']['max_lateral_tilt_change']['value']==0
    assert result['metrics']['left_arm']['wrist_peak_speed']['value']==pytest.approx(np.pi*.3,abs=.03)


def test_aspect_ratio_correction():
    a=analyze(synthetic(),1000,1000)
    b=analyze(synthetic(1600,900),1600,900)
    assert a['metrics']['left_arm']['shoulder_max']['value']==pytest.approx(b['metrics']['left_arm']['shoulder_max']['value'])


def test_low_confidence_never_interpreted():
    frames=synthetic()
    for f in frames:
        f['landmarks']['right_wrist']['confidence']=.1
    result=analyze(frames,1000,1000)
    assert result['metrics']['right_arm']['elbow_rom']['value'] is None
    assert result['asymmetry']['elbow_rom']['index_percent'] is None
    assert result['metrics']['left_arm']['elbow_rom']['value'] is not None


def test_missing_person_report_is_valid_json_without_guesses():
    frames=[{'timestamp':i/30,'landmarks':{},'people':0} for i in range(30)]
    report=build_report(analyze(frames,1280,720),{})
    json.dumps(report,allow_nan=False)
    assert report['observations']==[]
    assert report['clinical_context']==[]
    assert report['rehabilitation_options']==[]
    assert report['normalization']['scale_pixels'] is None
    assert all(m['value'] is None for arm in report['metrics'].values() for m in arm.values())


def test_missing_baseline_does_not_invent_trunk_change():
    frames=synthetic()
    for f in frames[:16]:
        f['landmarks'].pop('left_hip')
    assert analyze(frames,1000,1000)['metrics']['trunk']['max_lateral_tilt_change']['value'] is None


def test_gap_stays_null_in_timeseries():
    frames=synthetic()
    frames[45]['landmarks'].pop('left_elbow')
    report=build_report(analyze(frames,1000,1000),{})
    assert report['series'][45]['left_elbow_angle'] is None
    assert report['series'][44]['left_elbow_angle'] is not None
