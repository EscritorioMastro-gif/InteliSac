import Icon from "./Icon";

export default function BrandMark({ size = 34 }) {
  return (
    <div className="brand-mark" style={{ width: size, height: size }}>
      <Icon name="chat" size={size * 0.55} />
    </div>
  );
}
