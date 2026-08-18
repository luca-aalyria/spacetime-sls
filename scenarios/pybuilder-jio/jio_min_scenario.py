"""Jio-minimal SLS scenario: 200-satellite Walker constellation (20 planes x 10,
650 km, 48 deg) + 251 user terminals on India H3 res-3 cell centers + 3 India
gateways + PoP, with per-UT bidirectional SR-TE demand.

Generated for spacetime-sls ephemeral-instance testing (SANDBOX-LOCAL, not for
commit). Reuses simple_scenario's carrier configs, RF constants and PoP.
"""

from spacebox.archon.scenarios.pybuilder import simple_scenario as S
from spacebox.archon.scenarios.pybuilder.india_cells import INDIA_RES3_CENTERS

from github.tools.nbictl.proto import provisioning_pb2 as nbictl_provisioning_pb2
from nmts.v1.proto import nmts_pb2
from scenarios.builder.py.src.builders.components import (
  AntennaConnection,
  CategoryTag,
  FrontEndBuilder,
  ModemBuilder,
  NetworkNodeBuilder,
  PlatformBuilder,
  WiredLinkBuilder,
)
from scenarios.builder.py.src.builders.entity import (
  AntennaBuilder,
  DemodulatorBuilder,
  ModulatorBuilder,
  ReceiverBuilder,
  SignalChainBuilder,
  TransmitterBuilder,
)
from scenarios.builder.py.src.builders.provisioning import ProvisioningBuilder
from scenarios.builder.py.src.core import FragmentBuilder, ScenarioOutput, run
from scenarios.builder.py.src.orbits.motion_types import KeplerianElements

# Walker 200/20/1 @ 48 deg, 650 km
N_PLANES, SATS_PER_PLANE = 20, 10
ALTITUDE_M = 650_000
SEMIMAJOR_AXIS_M = 6_378_137 + ALTITUDE_M
INCLINATION_DEG = 48.0
PHASING_F = 1

GATEWAYS = [  # (id-suffix, name, lat, lon)
  ("mumbai", "Gateway Mumbai", 19.08, 72.88),
  ("chennai", "Gateway Chennai", 13.08, 80.27),
  ("delhi", "Gateway Delhi", 28.61, 77.21),
]


# fss01's user-beam (DRA) antennas carry a 75-deg conic field of regard. The
# link predictor's BeamCandidateAppointer only emits beam candidates for
# antennas that have a field of regard.
SAT_USER_FOR_HALF_ANGLE_DEG = 75.0


def _sat_ant_steerable(label, for_half_angle_deg=None):
  b = (
    AntennaBuilder()
    .with_label("antenna-type", label)
    .with_steerable()
    .with_pointing_format_cartesian(S.ITRF2020)
    .add_transmit_parabolic_gain_pattern(
      S.USER_ANTENNA_MAX_FREQ_HZ, S.USER_ANTENNA_DIAMETER_M,
      S.USER_ANTENNA_EFFICIENCY, S.USER_ANTENNA_BACKLOBE_GAIN_DB)
    .add_receive_parabolic_gain_pattern(
      S.USER_ANTENNA_MAX_FREQ_HZ, S.USER_ANTENNA_DIAMETER_M,
      S.USER_ANTENNA_EFFICIENCY, S.USER_ANTENNA_BACKLOBE_GAIN_DB)
  )
  if for_half_angle_deg is not None:
    b = b.with_field_of_regard_conic(for_half_angle_deg)
  return b


def build_satellite(i, plane, slot):
  sid = f"satellite-jio-{i + 1}"
  raan = plane * (360.0 / N_PLANES)
  ta = (slot * (360.0 / SATS_PER_PLANE)
        + plane * PHASING_F * (360.0 / (N_PLANES * SATS_PER_PLANE))) % 360.0
  return (
    PlatformBuilder(sid, CategoryTag.SATELLITE)
    .with_keplerian(KeplerianElements(
      semimajor_axis_m=SEMIMAJOR_AXIS_M, eccentricity=0.0,
      inclination_deg=INCLINATION_DEG, raan_deg=raan,
      argument_of_periapsis_deg=0.0, true_anomaly_deg=ta))
    .with_name(f"Jio Sat {i + 1} ({plane + 1}.{slot + 1})")
    .add_node(
      NetworkNodeBuilder(sid)
      .with_name(f"Jio Sat {i + 1}")
      .with_node_sid_mpls(40_000 + i)
      .with_router_id(f"10.1.{plane}.{slot + 1}"),
    )
    .add_antenna(f"{sid}-feeder-ant", _sat_ant_steerable("satellite-feeder"))
    .add_antenna(f"{sid}-user-downlink-ant",
                 _sat_ant_steerable("satellite-user", SAT_USER_FOR_HALF_ANGLE_DEG))
    .add_antenna(f"{sid}-user-uplink-ant",
                 _sat_ant_steerable("satellite-user", SAT_USER_FOR_HALF_ANGLE_DEG))
    .add_front_end(
      FrontEndBuilder(
        base_id=f"{sid}-feeder-fe",
        antennas=[AntennaConnection(
          antenna_id=f"{sid}-feeder-ant",
          transmitter=TransmitterBuilder(),
          receiver=ReceiverBuilder(),
          rx_spc=SignalChainBuilder().add_rectangular_filter(S.RX_FILTER_NOISE_TEMP_K),
          tx_carrier_config_id="carrier-config-satellite-feeder",
          rx_carrier_config_id="carrier-config-satellite-feeder")],
        modem=ModemBuilder(
          modulator=ModulatorBuilder()
          .with_point_to_point()
          .add_channel(S.FEEDER_CHANNEL_BW_HZ,
                       [S.FEEDER_SAT_TX_FREQ_HZ, S.FEEDER_SAT_TX_FREQ_2_HZ],
                       S.MODCODS, waveform=S.FEEDER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES),
          demodulator=DemodulatorBuilder()
          .with_point_to_point()
          .add_channel(S.FEEDER_CHANNEL_BW_HZ,
                       [S.FEEDER_GW_TX_FREQ_HZ, S.FEEDER_GW_TX_FREQ_2_HZ],
                       S.MODCODS, waveform=S.FEEDER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES),
          adjacency_sids_mpls=[50_000 + i]),
      ))
    .add_front_end(
      FrontEndBuilder(
        base_id=f"{sid}-user-dl-fe",
        antennas=[AntennaConnection(
          antenna_id=f"{sid}-user-downlink-ant",
          transmitter=TransmitterBuilder(),
          tx_carrier_config_id="carrier-config-satellite-user")],
        modem=ModemBuilder(
          modulator=ModulatorBuilder()
          .with_multiple_access()
          .add_channel(S.USER_CHANNEL_BW_HZ,
                       [S.USER_SAT_TX_FREQ_HZ, S.USER_SAT_TX_FREQ_2_HZ],
                       S.MODCODS, waveform=S.USER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES),
          adjacency_sids_mpls=[52_000 + i]),
      ))
    .add_front_end(
      FrontEndBuilder(
        base_id=f"{sid}-user-ul-fe",
        antennas=[AntennaConnection(
          antenna_id=f"{sid}-user-uplink-ant",
          receiver=ReceiverBuilder(),
          rx_spc=SignalChainBuilder().add_rectangular_filter(S.RX_FILTER_NOISE_TEMP_K),
          rx_carrier_config_id="carrier-config-satellite-user")],
        modem=ModemBuilder(
          demodulator=DemodulatorBuilder()
          .with_multiple_access()
          .add_channel(S.USER_CHANNEL_BW_HZ,
                       [S.USER_UT_TX_FREQ_HZ, S.USER_UT_TX_FREQ_2_HZ],
                       S.MODCODS, waveform=S.USER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES)),
      ))
  )


def build_gateway(g, suffix, name, lat, lon):
  gid = f"gateway-{suffix}"
  return (
    PlatformBuilder(gid, CategoryTag.GATEWAY)
    .at_position(latitude_deg=lat, longitude_deg=lon)
    .with_name(name)
    .add_node(
      NetworkNodeBuilder(gid)
      .with_name(name)
      .with_node_sid_mpls(39_000 + g)
      .with_router_id(f"10.0.1.{g + 1}")
      .add_interface("wan0", S.NetworkLayer.MPLS)
      .add_interface("wan1"),
    )
    .add_antenna(
      f"{gid}-feeder-ant",
      AntennaBuilder()
      .with_label("antenna-type", "gateway-feeder")
      .with_steerable()
      .with_field_of_regard_conic(S.GROUND_ANTENNA_FOR_HALF_ANGLE_DEG)
      .with_pointing_format_state_vector(S.ITRF2020)
      .add_transmit_parabolic_gain_pattern(
        S.FEEDER_ANTENNA_MAX_FREQ_HZ, S.FEEDER_ANTENNA_DIAMETER_M,
        S.FEEDER_ANTENNA_EFFICIENCY, S.FEEDER_ANTENNA_BACKLOBE_GAIN_DB)
      .add_receive_parabolic_gain_pattern(
        S.FEEDER_ANTENNA_MAX_FREQ_HZ, S.FEEDER_ANTENNA_DIAMETER_M,
        S.FEEDER_ANTENNA_EFFICIENCY, S.FEEDER_ANTENNA_BACKLOBE_GAIN_DB),
    )
    .add_front_end(
      FrontEndBuilder(
        base_id=f"{gid}-feeder-fe",
        antennas=[AntennaConnection(
          antenna_id=f"{gid}-feeder-ant",
          transmitter=TransmitterBuilder(),
          receiver=ReceiverBuilder(),
          rx_spc=SignalChainBuilder().add_rectangular_filter(S.RX_FILTER_NOISE_TEMP_K),
          tx_carrier_config_id="carrier-config-gateway-feeder",
          rx_carrier_config_id="carrier-config-gateway-feeder")],
        modem=ModemBuilder(
          modulator=ModulatorBuilder()
          .with_point_to_point()
          .add_channel(S.FEEDER_CHANNEL_BW_HZ, [S.FEEDER_GW_TX_FREQ_HZ],
                       S.MODCODS, waveform=S.FEEDER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES),
          demodulator=DemodulatorBuilder()
          .with_point_to_point()
          .add_channel(S.FEEDER_CHANNEL_BW_HZ, [S.FEEDER_SAT_TX_FREQ_HZ],
                       S.MODCODS, waveform=S.FEEDER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES),
          adjacency_sids_mpls=[49_000 + g]),
      ))
  )


def build_ut(j, lat, lon):
  uid = f"user-terminal-jio-{j + 1}"
  return (
    PlatformBuilder(uid, CategoryTag.USER_TERMINAL)
    .at_position(latitude_deg=lat, longitude_deg=lon)
    .with_name(f"Jio UT {j + 1}")
    .add_node(
      NetworkNodeBuilder(uid)
      .with_name(f"Jio UT {j + 1}")
      .with_node_sid_mpls(44_000 + j)
      .with_router_id(f"10.2.{j // 250}.{j % 250 + 1}"),
    )
    .add_antenna(
      f"{uid}-ant",
      AntennaBuilder()
      .with_label("antenna-type", "user-terminal")
      .with_steerable()
      .with_field_of_regard_conic(S.GROUND_ANTENNA_FOR_HALF_ANGLE_DEG)
      .with_pointing_format_state_vector(S.ITRF2020)
      .add_transmit_parabolic_gain_pattern(
        S.USER_ANTENNA_MAX_FREQ_HZ, S.USER_ANTENNA_DIAMETER_M,
        S.USER_ANTENNA_EFFICIENCY, S.USER_ANTENNA_BACKLOBE_GAIN_DB)
      .add_receive_parabolic_gain_pattern(
        S.USER_ANTENNA_MAX_FREQ_HZ, S.USER_ANTENNA_DIAMETER_M,
        S.USER_ANTENNA_EFFICIENCY, S.USER_ANTENNA_BACKLOBE_GAIN_DB),
    )
    .add_front_end(
      FrontEndBuilder(
        base_id=f"{uid}-fe",
        antennas=[AntennaConnection(
          antenna_id=f"{uid}-ant",
          transmitter=TransmitterBuilder(),
          receiver=ReceiverBuilder(),
          rx_spc=SignalChainBuilder().add_rectangular_filter(S.RX_FILTER_NOISE_TEMP_K),
          tx_carrier_config_id="carrier-config-user-terminal-user",
          rx_carrier_config_id="carrier-config-user-terminal-user")],
        modem=ModemBuilder(
          modulator=ModulatorBuilder()
          .with_point_to_point()
          .add_channel(S.USER_CHANNEL_BW_HZ, [S.USER_UT_TX_FREQ_HZ],
                       S.MODCODS, waveform=S.USER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES),
          demodulator=DemodulatorBuilder()
          .with_point_to_point()
          .add_channel(S.USER_CHANNEL_BW_HZ, [S.USER_SAT_TX_FREQ_HZ],
                       S.MODCODS, waveform=S.USER_WAVEFORM)
          .add_dvbs2_scrambling_codes(S.DVBS2_SCRAMBLING_CODES),
          shared_port=True,
          adjacency_sids_mpls=[54_000 + j]),
      ))
  )


def build_scenario():
  frags = {"carrier-configs": FragmentBuilder.of(*S.build_carrier_configs())}
  pop = S._build_pop()
  frags["pop"] = pop.build()

  gws = []
  for g, (suffix, name, lat, lon) in enumerate(GATEWAYS):
    gw = build_gateway(g, suffix, name, lat, lon)
    gws.append(gw)
    frags[f"gateway-{suffix}"] = gw.build()

  # wire each gateway to the PoP (wan0 <-> pop wan0/wan0-2/... use pop wan0 for first,
  # wan0-2 for second; add extra pop interfaces as needed)
  pop_ifaces = ["wan0", "wan0-2"]
  for g, gw in enumerate(gws):
    pop_if = pop_ifaces[g] if g < len(pop_ifaces) else "wan0"
    link = (
      WiredLinkBuilder(
        f"pop-gw-link-{g + 1}",
        interface_a_id=gw.node().interface_id("wan0"),
        interface_z_id=pop.interface_id(pop_if),
      )
      .with_max_data_rate_bps(S.WIRED_LINK_DATA_RATE_BPS)
      .enable_sr()
    )
    frags[f"pop-gw-link-{g + 1}"] = link.build()

  i = 0
  for plane in range(N_PLANES):
    for slot in range(SATS_PER_PLANE):
      sat = build_satellite(i, plane, slot)
      frags[f"satellite-jio-{i + 1}"] = sat.build()
      i += 1

  for j, (lat, lon) in enumerate(INDIA_RES3_CENTERS):
    frags[f"user-terminal-jio-{j + 1}"] = build_ut(j, lat, lon).build()

  return frags


def build_provisioning():
  resources = nbictl_provisioning_pb2.ProvisioningResources()
  for j in range(len(INDIA_RES3_CENTERS)):
    uid = f"user-terminal-jio-{j + 1}"
    policies, candidate_paths = ProvisioningBuilder.create_bidirectional(
      policy_id_forward=f"pop-route-fn--{uid}-route-fn",
      policy_id_reverse=f"{uid}-route-fn--pop-route-fn",
      node_a="pop-route-fn",
      node_b=f"{uid}-route-fn",
      color=1,
      cir_bps=100_000,
      preference=1,
    )
    resources.p2p_sr_te_policies.extend(policies)
    resources.p2p_sr_te_policy_candidate_paths.extend(candidate_paths)
  return resources


def _build(args) -> ScenarioOutput:
  del args
  return ScenarioOutput(
    fragments=build_scenario(),
    provisioning={"provisioning": build_provisioning()},
  )


def main():
  run(_build, description=__doc__)


if __name__ == "__main__":
  main()
