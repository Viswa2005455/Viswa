/** Decorative 3D backdrop behind the whole app: a perspective grid floor, two slowly turning wireframe
 * cubes, a ring and soft light. CSS transforms only (GPU-composited, no 3D library); content always
 * sits on solid cards in front of it. Hidden from assistive technology; still under reduced motion. */
function Cube({ className }: { className: string }) {
  return <div className={`bg-cube ${className}`}><i /><i /><i /><i /><i /><i /></div>;
}

export function Background3D() {
  return (
    <div className="app-bg" aria-hidden="true">
      <div className="bg-light a" />
      <div className="bg-light b" />
      <div className="bg-stage">
        <div className="bg-floor"><div className="bg-grid" /></div>
        <Cube className="c1" />
        <Cube className="c2" />
        <div className="bg-ring" />
      </div>
    </div>
  );
}
