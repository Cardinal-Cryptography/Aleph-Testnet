use libp2p::{
    identity::{self, Keypair},
    PeerId,
};
fn main() {
    let authorities = [
        "Damian", "Tomasz", "Zbyszko", "Hansu", "Adam", "Matt", "Antoni", "Michal",
    ];

    let keys = (0..8)
        .map(|_| identity::ed25519::Keypair::generate())
        .collect::<Vec<_>>();
    for (auth, key) in authorities.iter().zip(keys.iter()) {
        std::fs::write(
            "data/".to_owned() + auth + "/libp2p_secret",
            key.secret().as_ref(),
        )
        .expect("should succeed");
    }
    let publics = keys
        .into_iter()
        .map(|k| PeerId::from_public_key(Keypair::Ed25519(k).public()).to_string())
        .collect::<Vec<_>>()
        .join('\n'.to_string().as_str());
    std::fs::write("data/libp2p2_public_keys", publics).expect("should succeed");
}
