import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as THREE from 'three';
import {
  DigitalTwin,
  VerticalUnit,
  FloorLevel,
  Building,
  UndergroundVolume,
  ElevatedVolume,
} from '../../types/api.ts';
import { LayerVisibilityState } from './LayerControl.tsx';
import { SelectedCadastralItem } from './PropertyInspector.tsx';

interface DigitalTwinViewerProps {
  digitalTwin: DigitalTwin;
  layers: LayerVisibilityState;
  wireframe: boolean;
  selectedItem: SelectedCadastralItem;
  onSelectItem: (item: SelectedCadastralItem) => void;
  resetViewTrigger?: number;
}

/**
 * Extracts a 2D ring of [x, y] or [lon, lat] coordinates from GeoJSON or polygon arrays.
 */
function extractRingCoordinates(geom: any): [number, number][] {
  if (!geom) return [];
  if (Array.isArray(geom)) {
    if (geom.length === 0) return [];
    if (typeof geom[0][0] === 'number') return geom as [number, number][];
    if (Array.isArray(geom[0]) && typeof geom[0][0][0] === 'number') return geom[0] as [number, number][];
  }
  if (geom.coordinates && Array.isArray(geom.coordinates)) {
    const coords = geom.coordinates;
    if (coords.length === 0) return [];
    if (Array.isArray(coords[0])) {
      if (typeof coords[0][0] === 'number') return coords as [number, number][];
      if (Array.isArray(coords[0][0]) && typeof coords[0][0][0] === 'number') return coords[0] as [number, number][];
    }
  }
  return [];
}

export const DigitalTwinViewer: React.FC<DigitalTwinViewerProps> = ({
  digitalTwin,
  layers,
  wireframe,
  selectedItem,
  onSelectItem,
  resetViewTrigger,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const meshesGroupRef = useRef<THREE.Group | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);
  const interactionObjectsRef = useRef<{ mesh: THREE.Mesh; item: SelectedCadastralItem }[]>([]);
  const isInteractingRef = useRef<boolean>(false);
  const [hoveredLabel, setHoveredLabel] = useState<string | null>(null);

  // Derive base elevation datum (AMSL)
  const baseElevation = useMemo(() => {
    const p = digitalTwin.parcel;
    return (
      p.ground_elevation_amsl ??
      p.base_elevation_m ??
      (digitalTwin.buildings[0]?.ground_elevation_m || 0)
    );
  }, [digitalTwin]);

  // Spatial Projection Parameters: Center and Metric Scale
  const projectionParams = useMemo(() => {
    const parcelCoords = extractRingCoordinates(
      digitalTwin.parcel.geometry_geojson || (digitalTwin.parcel as any).coordinates
    );

    const bldgCoords: [number, number][] = [];
    digitalTwin.buildings.forEach((b) => {
      bldgCoords.push(...extractRingCoordinates(b.footprint_geojson));
    });

    const allCoords = [...parcelCoords, ...bldgCoords];

    if (allCoords.length === 0) {
      return {
        centerX: 0,
        centerY: 0,
        metersPerLon: 1,
        metersPerLat: 1,
        spanMeters: 50,
      };
    }

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    allCoords.forEach(([x, y]) => {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    });

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    const isGeographic = Math.abs(centerX) <= 180 && Math.abs(centerY) <= 90;
    const metersPerLat = isGeographic ? 111320 : 1;
    const metersPerLon = isGeographic
      ? 111320 * Math.cos((centerY * Math.PI) / 180)
      : 1;

    const spanMeters = Math.max(
      (maxX - minX) * metersPerLon,
      (maxY - minY) * metersPerLat,
      30
    );

    return { centerX, centerY, metersPerLon, metersPerLat, spanMeters };
  }, [digitalTwin]);

  // Orbit control states
  const mouseState = useRef({
    isDown: false,
    button: 0,
    prevX: 0,
    prevY: 0,
    theta: Math.PI / 4,
    phi: Math.PI / 3.2,
    radius: 40,
    target: new THREE.Vector3(0, 4, 0),
  });

  const updateCameraPosition = () => {
    if (!cameraRef.current) return;
    const { theta, phi, radius, target } = mouseState.current;
    cameraRef.current.position.x = target.x + radius * Math.sin(phi) * Math.sin(theta);
    cameraRef.current.position.y = target.y + radius * Math.cos(phi);
    cameraRef.current.position.z = target.z + radius * Math.sin(phi) * Math.cos(theta);
    cameraRef.current.lookAt(target);
  };

  // Reset view to optimal isometric perspective adapted to parcel dimension
  const resetCamera = () => {
    const span = projectionParams.spanMeters;
    const avgHeight = digitalTwin.buildings[0]?.total_height_m || 18;
    mouseState.current.theta = Math.PI / 4;
    mouseState.current.phi = Math.PI / 3.4;
    mouseState.current.radius = Math.max(30, span * 1.25);
    mouseState.current.target.set(0, avgHeight * 0.35, 0);
    updateCameraPosition();
  };

  useEffect(() => {
    resetCamera();
  }, [resetViewTrigger, projectionParams.spanMeters]);

  // Initialize Three.js scene
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;

    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0x18191b);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    cameraRef.current = camera;
    updateCameraPosition();

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    rendererRef.current = renderer;

    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // Warm geographic survey lighting
    const ambientLight = new THREE.AmbientLight(0xfff5ea, 0.8);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffeedd, 1.25);
    dirLight.position.set(45, 60, 35);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    scene.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0x7c9d83, 0.45);
    fillLight.position.set(-35, 25, -35);
    scene.add(fillLight);

    // Cadastral Ground Datum Grid & Group
    const gridHelper = new THREE.GridHelper(100, 40, 0x4e555e, 0x25282c);
    gridHelper.position.y = 0;
    gridHelperRef.current = gridHelper;
    scene.add(gridHelper);

    const meshesGroup = new THREE.Group();
    meshesGroupRef.current = meshesGroup;
    scene.add(meshesGroup);

    // Animation Loop
    let animationFrameId: number;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      if (rendererRef.current && sceneRef.current && cameraRef.current) {
        rendererRef.current.render(sceneRef.current, cameraRef.current);
      }
    };
    animate();

    // Resize Observer
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width: w, height: h } = entry.contentRect;
        if (w > 0 && h > 0 && cameraRef.current && rendererRef.current) {
          cameraRef.current.aspect = w / h;
          cameraRef.current.updateProjectionMatrix();
          rendererRef.current.setSize(w, h);
        }
      }
    });
    resizeObserver.observe(container);

    // Mouse Interaction Handlers
    const onMouseDown = (e: MouseEvent) => {
      mouseState.current.isDown = true;
      mouseState.current.button = e.button;
      mouseState.current.prevX = e.clientX;
      mouseState.current.prevY = e.clientY;
      isInteractingRef.current = false;
    };

    const onMouseMove = (e: MouseEvent) => {
      const containerRect = container.getBoundingClientRect();
      const mouseX = ((e.clientX - containerRect.left) / containerRect.width) * 2 - 1;
      const mouseY = -((e.clientY - containerRect.top) / containerRect.height) * 2 + 1;

      if (mouseState.current.isDown) {
        isInteractingRef.current = true;
        const deltaX = e.clientX - mouseState.current.prevX;
        const deltaY = e.clientY - mouseState.current.prevY;
        mouseState.current.prevX = e.clientX;
        mouseState.current.prevY = e.clientY;

        if (mouseState.current.button === 0) {
          // Orbit
          mouseState.current.theta -= deltaX * 0.008;
          mouseState.current.phi = Math.max(
            0.1,
            Math.min(Math.PI / 2 + 0.35, mouseState.current.phi - deltaY * 0.008)
          );
        } else if (mouseState.current.button === 2) {
          // Pan
          const panSpeed = 0.035;
          const forward = new THREE.Vector3();
          camera.getWorldDirection(forward);
          const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
          const up = camera.up.clone().normalize();

          mouseState.current.target.addScaledVector(right, -deltaX * panSpeed);
          mouseState.current.target.addScaledVector(up, deltaY * panSpeed);
        }
        updateCameraPosition();
        return;
      }

      // Raycast for Hover Feedback
      if (!cameraRef.current || !sceneRef.current) return;
      const raycaster = new THREE.Raycaster();
      raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), cameraRef.current);
      const meshesToTest = interactionObjectsRef.current.map((obj) => obj.mesh);
      const intersects = raycaster.intersectObjects(meshesToTest, false);

      if (intersects.length > 0) {
        const hitMesh = intersects[0].object as THREE.Mesh;
        const entry = interactionObjectsRef.current.find((o) => o.mesh === hitMesh);
        if (entry) {
          if (entry.item?.type === 'unit') {
            setHoveredLabel(
              `${entry.item.data.classification || entry.item.data.unit_type} (${entry.item.data.ulpin_3d})`
            );
          } else if (entry.item?.type === 'floor') {
            setHoveredLabel(entry.item.data.level_name || `Floor Level ${entry.item.data.level_code}`);
          } else if (entry.item?.type === 'building') {
            setHoveredLabel(entry.item.data.building_name);
          } else if (entry.item?.type === 'parcel') {
            setHoveredLabel(`Base Parcel ULPIN: ${entry.item.data.ulpin}`);
          }
          container.style.cursor = 'pointer';
          return;
        }
      }
      setHoveredLabel(null);
      container.style.cursor = 'default';
    };

    const onMouseUp = (e: MouseEvent) => {
      mouseState.current.isDown = false;
      if (!isInteractingRef.current && cameraRef.current) {
        const containerRect = container.getBoundingClientRect();
        const mouseX = ((e.clientX - containerRect.left) / containerRect.width) * 2 - 1;
        const mouseY = -((e.clientY - containerRect.top) / containerRect.height) * 2 + 1;

        const raycaster = new THREE.Raycaster();
        raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), cameraRef.current);
        const meshesToTest = interactionObjectsRef.current.map((obj) => obj.mesh);
        const intersects = raycaster.intersectObjects(meshesToTest, false);

        if (intersects.length > 0) {
          const hitMesh = intersects[0].object as THREE.Mesh;
          const entry = interactionObjectsRef.current.find((o) => o.mesh === hitMesh);
          if (entry) {
            onSelectItem(entry.item);
          }
        }
      }
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      mouseState.current.radius = Math.max(
        10,
        Math.min(250, mouseState.current.radius + e.deltaY * 0.04)
      );
      updateCameraPosition();
    };

    const onContextMenu = (e: MouseEvent) => e.preventDefault();

    container.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    container.addEventListener('wheel', onWheel, { passive: false });
    container.addEventListener('contextmenu', onContextMenu);

    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      container.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      container.removeEventListener('wheel', onWheel);
      container.removeEventListener('contextmenu', onContextMenu);
      renderer.dispose();
    };
  }, []);

  // Rebuild 3D Cadastral Geometry dynamically from real backend GeoJSON
  useEffect(() => {
    const group = meshesGroupRef.current;
    if (!group) return;

    // Clear existing meshes
    while (group.children.length > 0) {
      const obj = group.children[0];
      group.remove(obj);
      if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
        obj.geometry.dispose();
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose());
        } else {
          obj.material.dispose();
        }
      }
    }
    interactionObjectsRef.current = [];

    const { centerX, centerY, metersPerLon, metersPerLat, spanMeters } = projectionParams;

    // Helper: convert [lon, lat] coordinate to local metric X and Z
    const toLocal = (coord: [number, number]) => {
      const [lon, lat] = coord;
      const x = (lon - centerX) * metersPerLon;
      const z = -(lat - centerY) * metersPerLat;
      return { x, z };
    };

    // Helper: construct THREE.Shape from polygon coordinates
    const makeShape = (coords: [number, number][]): THREE.Shape => {
      const shape = new THREE.Shape();
      if (!coords || coords.length === 0) return shape;
      coords.forEach((coord, i) => {
        const { x, z } = toLocal(coord);
        if (i === 0) shape.moveTo(x, -z);
        else shape.lineTo(x, -z);
      });
      shape.closePath();
      return shape;
    };

    // Update GridHelper size to encompass parcel
    if (gridHelperRef.current) {
      const gridDim = Math.max(80, Math.ceil((spanMeters * 2.2) / 20) * 20);
      gridHelperRef.current.scale.set(gridDim / 100, 1, gridDim / 100);
    }

    const isSelected = (type: string, id: string) => {
      if (!selectedItem) return false;
      return selectedItem.type === type && (selectedItem.data as any).id === id;
    };

    // Extract real parcel boundary
    const parcelRawCoords = extractRingCoordinates(
      digitalTwin.parcel.geometry_geojson || (digitalTwin.parcel as any).coordinates
    );

    // Real parcel boundary from backend GeoJSON
    const parcelCoords =
      parcelRawCoords.length > 2 ? parcelRawCoords : [];

    // Primary Building Footprint from backend GeoJSON
    const primaryBuilding = digitalTwin.buildings[0];
    const bldgRawCoords = primaryBuilding
      ? extractRingCoordinates(primaryBuilding.footprint_geojson)
      : [];
    const bldgCoords = bldgRawCoords.length > 2 ? bldgRawCoords : [];

    // 1. Base Parcel Ground Layer (Real GeoJSON Polygon)
    if (layers.parcel && parcelCoords.length > 2) {
      const parcelShape = makeShape(parcelCoords);
      const geom = new THREE.ShapeGeometry(parcelShape);
      geom.rotateX(-Math.PI / 2);
      const isParcelSelected = selectedItem?.type === 'parcel';

      const mat = new THREE.MeshStandardMaterial({
        color: isParcelSelected ? 0x7c9d83 : 0x2d352e,
        roughness: 0.9,
        metalness: 0.1,
        wireframe,
      });

      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.y = -0.05;
      mesh.receiveShadow = true;
      group.add(mesh);

      // Real boundary perimeter line
      const edges = new THREE.EdgesGeometry(geom);
      const line = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({
          color: isParcelSelected ? 0xd97757 : 0x6b8e72,
          linewidth: 2,
        })
      );
      line.position.y = 0.01;
      group.add(line);

      // Real Boundary Survey Beacons placed at true parcel polygon vertices
      const beaconGeom = new THREE.CylinderGeometry(0.35, 0.45, 0.9, 8);
      const beaconMat = new THREE.MeshStandardMaterial({ color: 0xd97757 });
      parcelCoords.forEach((pt) => {
        const { x, z } = toLocal(pt);
        const bMesh = new THREE.Mesh(beaconGeom, beaconMat);
        bMesh.position.set(x, 0.45, z);
        group.add(bMesh);
      });

      interactionObjectsRef.current.push({
        mesh,
        item: { type: 'parcel', data: digitalTwin.parcel },
      });
    }

    // 2. Building Outer Envelope (Real Footprint Extrusion)
    if (layers.building && primaryBuilding && bldgCoords.length > 2) {
      const bldgShape = makeShape(bldgCoords);
      const bldgHeight =
        primaryBuilding.total_height_m ||
        primaryBuilding.total_height ||
        18.0;

      const bGeom = new THREE.ExtrudeGeometry(bldgShape, {
        depth: Math.max(1, bldgHeight),
        bevelEnabled: false,
      });
      bGeom.rotateX(-Math.PI / 2);

      const bEdges = new THREE.EdgesGeometry(bGeom);
      const bWire = new THREE.LineSegments(
        bEdges,
        new THREE.LineBasicMaterial({
          color: selectedItem?.type === 'building' ? 0xd97757 : 0x5c7080,
          transparent: true,
          opacity: 0.45,
        })
      );
      const bldgRelY = (primaryBuilding.ground_elevation_m ?? baseElevation) - baseElevation;
      bWire.position.set(0, bldgRelY, 0);
      group.add(bWire);
    }

    // 3. Floor Slabs (Extruded from real floor elevations)
    if (layers.floors && bldgCoords.length > 2) {
      digitalTwin.floors.forEach((floor: FloorLevel) => {
        const floorZ = floor.elevation_min_m ?? floor.elevation_bottom ?? baseElevation;
        const relFloorY = floorZ - baseElevation;

        // Underground floor layer filter
        if (!layers.underground && (floor.is_underground || floor.is_basement || relFloorY < 0)) return;

        const flCoords = extractRingCoordinates(floor.footprint_geojson);
        const slabCoords = flCoords.length > 2 ? flCoords : bldgCoords;
        const flFloorShape = makeShape(slabCoords);

        const slabGeom = new THREE.ExtrudeGeometry(flFloorShape, {
          depth: 0.2,
          bevelEnabled: false,
        });
        slabGeom.rotateX(-Math.PI / 2);
        const isFloorSelected = isSelected('floor', floor.id);

        const slabMat = new THREE.MeshStandardMaterial({
          color: isFloorSelected ? 0xd97757 : floor.is_underground ? 0x2b2e34 : 0x41464f,
          roughness: 0.7,
          metalness: 0.2,
          wireframe,
        });

        const slabMesh = new THREE.Mesh(slabGeom, slabMat);
        slabMesh.position.set(0, relFloorY, 0);
        slabMesh.receiveShadow = true;
        group.add(slabMesh);

        interactionObjectsRef.current.push({
          mesh: slabMesh,
          item: { type: 'floor', data: floor },
        });
      });
    }

    // 4. Vertical Units (3D Volumetric Prisms Extruded from Real Unit Footprints)
    if (layers.units) {
      digitalTwin.units.forEach((unit: VerticalUnit) => {
        const rawUnitCoords = extractRingCoordinates(unit.footprint_geojson);
        const unitCoords = rawUnitCoords.length > 2 ? rawUnitCoords : bldgCoords;
        if (unitCoords.length < 3) return; // Do not render if no valid geometry

        const zMin = unit.elevation_min_m ?? unit.vertical_range?.z_min ?? baseElevation;
        const zMax =
          unit.elevation_max_m ??
          unit.vertical_range?.z_max ??
          (zMin + 3.5);

        const relYMin = zMin - baseElevation;
        const relYMax = zMax - baseElevation;
        const height = Math.max(0.2, relYMax - relYMin);

        // Underground layer visibility filter
        if (
          !layers.underground &&
          (relYMin < 0 ||
            unit.unit_type === 'UNDERGROUND_VAULT' ||
            unit.unit_type === 'PARKING' ||
            unit.vertical_classification === 'UNDERGROUND')
        ) {
          return;
        }

        // Shared / Common layer visibility filter
        if (
          !layers.sharedCommon &&
          (unit.unit_type === 'COMMON_AREA' ||
            unit.unit_type === 'COMMON_PROPERTY' ||
            unit.vertical_classification === 'COMMON_PROPERTY')
        ) {
          return;
        }

        const unitShape = makeShape(unitCoords);
        const unitGeom = new THREE.ExtrudeGeometry(unitShape, {
          depth: Math.max(0.1, height - 0.08),
          bevelEnabled: false,
        });
        unitGeom.rotateX(-Math.PI / 2);

        const isUnitSelected = isSelected('unit', unit.id);

        // Classification-based color styling
        let baseColor = 0xc86446; // Terracotta default
        let opacity = 0.85;

        if (unit.unit_type === 'COMMERCIAL') {
          baseColor = 0x9c6b48; // Warm copper
        } else if (
          unit.unit_type === 'COMMON_AREA' ||
          unit.unit_type === 'COMMON_PROPERTY'
        ) {
          baseColor = 0x657885; // Muted slate blue-grey
        } else if (
          unit.unit_type === 'UNDERGROUND_VAULT' ||
          unit.unit_type === 'PARKING'
        ) {
          baseColor = 0x4e555e; // Subsurface stone
        } else if (
          unit.unit_type === 'ELEVATED_AIR_RIGHTS' ||
          unit.unit_type === 'TERRACE'
        ) {
          baseColor = 0x6b8e72; // Sage green
          opacity = 0.6;
        } else if (unit.unit_number.endsWith('02')) {
          baseColor = 0xd47b58; // Secondary terracotta
        }

        if (isUnitSelected) {
          baseColor = 0xf08a65;
          opacity = 1.0;
        }

        const unitMat = new THREE.MeshStandardMaterial({
          color: baseColor,
          roughness: 0.55,
          metalness: 0.15,
          transparent: opacity < 1.0,
          opacity: isUnitSelected ? 1.0 : opacity,
          wireframe,
        });

        const unitMesh = new THREE.Mesh(unitGeom, unitMat);
        unitMesh.position.set(0, relYMin + 0.04, 0);
        unitMesh.castShadow = true;
        unitMesh.receiveShadow = true;
        group.add(unitMesh);

        // Precise cadastral boundary edges
        const edges = new THREE.EdgesGeometry(unitGeom);
        const edgeLine = new THREE.LineSegments(
          edges,
          new THREE.LineBasicMaterial({
            color: isUnitSelected ? 0xffffff : 0x222428,
            linewidth: isUnitSelected ? 2 : 1,
          })
        );
        edgeLine.position.copy(unitMesh.position);
        group.add(edgeLine);

        interactionObjectsRef.current.push({
          mesh: unitMesh,
          item: { type: 'unit', data: unit },
        });
      });
    }

    // 5. Explicit Underground Sub-surface Volumes (if provided)
    if (layers.underground && digitalTwin.underground_volumes) {
      digitalTwin.underground_volumes.forEach((ug: UndergroundVolume) => {
        const ugCoords = ug.footprint ? ug.footprint : bldgCoords;
        const ugShape = makeShape(ugCoords);
        const zMin = ug.vertical_range.z_min;
        const zMax = ug.vertical_range.z_max;
        const h = Math.max(0.2, zMax - zMin);
        const relY = zMin - baseElevation;

        const ugGeom = new THREE.ExtrudeGeometry(ugShape, {
          depth: h,
          bevelEnabled: false,
        });
        ugGeom.rotateX(-Math.PI / 2);
        const isUgSelected = isSelected('underground', ug.id);

        const ugMat = new THREE.MeshStandardMaterial({
          color: isUgSelected ? 0xd97757 : 0x363a40,
          roughness: 0.9,
          metalness: 0.1,
          transparent: true,
          opacity: 0.6,
          wireframe,
        });

        const ugMesh = new THREE.Mesh(ugGeom, ugMat);
        ugMesh.position.set(0, relY, 0);
        group.add(ugMesh);

        interactionObjectsRef.current.push({
          mesh: ugMesh,
          item: { type: 'underground', data: ug },
        });
      });
    }

    // 6. Explicit Elevated Air Rights / Easement Volumes (if provided)
    if (digitalTwin.elevated_volumes) {
      digitalTwin.elevated_volumes.forEach((el: ElevatedVolume) => {
        const elCoords = el.footprint ? el.footprint : bldgCoords;
        const elShape = makeShape(elCoords);
        const zMin = el.vertical_range.z_min;
        const zMax = el.vertical_range.z_max;
        const h = Math.max(0.2, zMax - zMin);
        const relY = zMin - baseElevation;

        const elGeom = new THREE.ExtrudeGeometry(elShape, {
          depth: h,
          bevelEnabled: false,
        });
        elGeom.rotateX(-Math.PI / 2);
        const isElSelected = isSelected('elevated', el.id);

        const elMat = new THREE.MeshStandardMaterial({
          color: isElSelected ? 0xd97757 : 0x6b8e72,
          roughness: 0.4,
          metalness: 0.2,
          transparent: true,
          opacity: isElSelected ? 0.65 : 0.25,
          wireframe,
        });

        const elMesh = new THREE.Mesh(elGeom, elMat);
        elMesh.position.set(0, relY, 0);
        group.add(elMesh);

        interactionObjectsRef.current.push({
          mesh: elMesh,
          item: { type: 'elevated', data: el },
        });
      });
    }
  }, [digitalTwin, layers, wireframe, selectedItem, projectionParams, baseElevation]);

  return (
    <div className="relative w-full h-full min-h-[460px] bg-[#18191b] rounded-lg overflow-hidden border border-[#2d3034]">
      {/* 3D Canvas Mount Point */}
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Floating Hover Label */}
      {hoveredLabel && (
        <div className="absolute top-4 left-4 pointer-events-none bg-[#1c1d20]/90 border border-[#34373d] px-3 py-1.5 rounded text-xs font-mono text-[#f4f3ef] shadow-lg">
          {hoveredLabel}
        </div>
      )}

      {/* Viewport Cadastral Compass & Controls Indicator */}
      <div className="absolute bottom-3 left-3 pointer-events-none text-[11px] text-[#a09f99]/80 bg-[#1c1d20]/80 px-2.5 py-1 rounded border border-[#2d3034] space-x-3">
        <span>Orbit: Left Drag</span>
        <span>•</span>
        <span>Pan: Right Drag</span>
        <span>•</span>
        <span>Zoom: Scroll</span>
      </div>

      <div className="absolute bottom-3 right-3 pointer-events-none text-[11px] font-mono text-[#a09f99]/80 bg-[#1c1d20]/80 px-2 py-0.5 rounded border border-[#2d3034]">
        Datum: {digitalTwin.metadata.datum || digitalTwin.parcel.crs || 'WGS84 / Metric UTM'}
      </div>
    </div>
  );
};
