from __future__ import annotations
import streamlit as st

from core.models.schema import Target


def render() -> Target | None:
    with st.form("target_form", clear_on_submit=False):
        st.subheader("Target")
        c1, c2 = st.columns(2)
        email = c1.text_input("Email")
        phone = c2.text_input("Phone (E.164)")
        name = c1.text_input("Full name")
        username = c2.text_input("Username / handle")
        domain = c1.text_input("Domain")
        company = c2.text_input("Company")
        location = c1.text_input("Location hint")
        image = c2.file_uploader("Image (for EXIF)", type=["jpg", "jpeg", "png", "tiff"])

        submit = st.form_submit_button("Investigate", use_container_width=True)
        if submit:
            kw = {
                "email": email or None,
                "phone": phone or None,
                "name": name or None,
                "username": username or None,
                "domain": domain or None,
                "company": company or None,
                "location": location or None,
            }
            kw = {k: v for k, v in kw.items() if v}
            if image:
                tmp = f"/tmp/{image.name}"
                with open(tmp, "wb") as f:
                    f.write(image.getbuffer())
                kw["image_path"] = tmp
            if not kw:
                st.warning("Provide at least one identifier.")
                return None
            return Target(**kw)
    return None
