# ============ CONTINUACIÓN DEL CÓDIGO ============

# ---------------- UI: REGISTRAR ATENCION ----------------
def ui_cargar_datos(auth_user: Optional[str]):
    st.subheader("Registrar atención / paciente")

    def K(x: str) -> str:
        return f"reg_{x}"

    defaults = {
        K("pac_nombre"): "",
        K("pac_fecha_nac"): "",
        K("pac_telefono"): "",
        K("pac_email"): "",
        K("pac_direccion"): "",
        K("pac_localidad"): "",
        K("pac_municipio"): "",
        K("pac_departamento"): "",
        K("pac_sexo"): "(No especifica)",
        K("pac_zona"): "(No especifica)",
        K("pac_id_actual"): None,
        K("pac_doc"): "",
        K("pac_creado_panacea"): False,
        K("pac_priorizado"): False,
        K("priorizado_origen"): "(Seleccione)",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    c1, c2 = st.columns([1.4, 1.4])
    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = c1.selectbox("Programa", options=list(prog_map.keys()) if prog_map else [], key=K("form_programa"))
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else pd.DataFrame()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = c1.selectbox("Convenio", options=list(conv_map.keys()) if conv_map else [], key=K("form_convenio"))
    cid = conv_map.get(csel)

    prof = DATA.list_Profesionales(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c2.selectbox("Profesional", options=list(prof_map.keys()) if prof_map else [], key=K("form_profesional"))
    fid = prof_map.get(fsel)

    instituciones = DATA.list_instituciones()
    institucion_id = None
    localidad_val = municipio_val = departamento_val = None

    st.markdown("#### Ubicación e institución")
    if instituciones.empty:
        st.info("No hay instituciones configuradas. Crea instituciones en Configuración.")
    else:
        g1, g2, g3, g4 = st.columns([1, 1, 1, 2])
        deps = sorted({str(x) for x in instituciones["departamento"].dropna().unique()})
        dep_sel = g1.selectbox("Departamento", options=deps, key=K("departamento_sel")) if deps else None

        inst_dep = instituciones if not dep_sel else instituciones[instituciones["departamento"] == dep_sel]
        muns = sorted({str(x) for x in inst_dep["municipio"].dropna().unique()})
        mun_sel = g2.selectbox("Municipio", options=["(Todos)"] + muns, key=K("municipio_sel")) if muns else "(Todos)"

        inst_mun = inst_dep if mun_sel == "(Todos)" else inst_dep[inst_dep["municipio"] == mun_sel]
        locs = sorted({str(x) for x in inst_mun["localidad"].dropna().unique()})
        loc_label = "Localidad (Bogotá)" if dep_sel and "BOGOTA" in dep_sel.upper() else "Localidad"
        loc_sel = g3.selectbox(loc_label, options=["(Todas)"] + locs, key=K("localidad_sel")) if locs else "(Todas)"

        inst_geo = inst_mun if loc_sel == "(Todas)" else inst_mun[inst_mun["localidad"] == loc_sel]
        inst_map = {r["nombre"]: int(r["id"]) for _, r in inst_geo.iterrows()}
        inst_sel = g4.selectbox("Institución", options=list(inst_map.keys()) if inst_map else [], key=K("institucion_sel"))
        institucion_id = inst_map.get(inst_sel)
        if institucion_id:
            row = instituciones[instituciones["id"] == institucion_id].iloc[0]
            localidad_val = row.get("localidad")
            municipio_val = row.get("municipio")
            departamento_val = row.get("departamento")

    c3, c4 = st.columns([1, 1])
    fecha = c3.date_input("Fecha de la atención", value=date.today(), key=K("fecha"))
    actividad = c4.selectbox("Actividad / plantilla", ACTIVIDADES_PLANTILLAS, key=K("actividad"))

    st.markdown("#### Datos del paciente")
    p1, p2 = st.columns([1, 1])
    p1.text_input("Documento del paciente (cédula)", key=K("pac_doc"))
    if p2.button("Buscar paciente por documento", key=K("btn_buscar_paciente")):
        try:
            doc_trim = (st.session_state[K("pac_doc")] or "").strip()
            pac = DATA.get_paciente_por_documento(doc_trim)
            if pac:
                st.session_state[K("pac_id_actual")] = pac.get("id")
                st.session_state[K("pac_nombre")] = pac.get("nombre", "") or ""
                st.session_state[K("pac_sexo")] = pac.get("sexo") if pac.get("sexo") in ["F", "M", "Otro"] else "(No especifica)"
                st.session_state[K("pac_fecha_nac")] = pac.get("fecha_nacimiento", "") or ""
                st.session_state[K("pac_telefono")] = pac.get("telefono", "") or ""
                st.session_state[K("pac_email")] = pac.get("email", "") or ""
                st.session_state[K("pac_direccion")] = pac.get("direccion", "") or ""
                st.session_state[K("pac_localidad")] = pac.get("localidad", "") or ""
                st.session_state[K("pac_municipio")] = pac.get("municipio", "") or ""
                st.session_state[K("pac_departamento")] = pac.get("departamento", "") or ""
                st.session_state[K("pac_zona")] = pac.get("zona") if pac.get("zona") in ["Urbana", "Rural"] else "(No especifica)"
                success_toast("Paciente encontrado. Campos autocompletados.")
                st.rerun()
            else:
                st.session_state[K("pac_id_actual")] = None
                warn_toast("No se encontró paciente. Diligencia y se creará.")
        except Exception as e:
            error_toast(f"Error buscando paciente: {e}")

    p3, p4 = st.columns([1.5, 1])
    p3.text_input("Nombre completo del paciente", key=K("pac_nombre"))
    sexo_opts = ["(No especifica)", "F", "M", "Otro"]
    st.session_state.setdefault(K("pac_sexo"), "(No especifica)")
    p4.selectbox("Sexo (opcional)", options=sexo_opts, key=K("pac_sexo"))

    p5, p6 = st.columns([1, 1])
    p5.text_input("Fecha de nacimiento (AAAA-MM-DD, opcional)", key=K("pac_fecha_nac"))
    p6.text_input("Teléfono (opcional)", key=K("pac_telefono"))

    p7, p8 = st.columns([1, 1])
    p7.text_input("Email (opcional)", key=K("pac_email"))
    p8.text_input("Dirección (opcional)", key=K("pac_direccion"))

    p9, p10, p11 = st.columns([1, 1, 1])
    p9.text_input("Localidad paciente (opcional)", key=K("pac_localidad"))
    p10.text_input("Municipio paciente (opcional)", key=K("pac_municipio"))
    p11.text_input("Departamento paciente (opcional)", key=K("pac_departamento"))

    zcol, zcol2 = st.columns([1, 1])
    zona_opts = ["(No especifica)", "Urbana", "Rural"]
    st.session_state.setdefault(K("pac_zona"), "(No especifica)")
    zcol.selectbox("Zona (Rural/Urbana)", options=zona_opts, key=K("pac_zona"))

    zcol2.checkbox("Paciente creado en Panacea", key=K("pac_creado_panacea"))
    c9, c10 = st.columns([1, 1])
    c9.radio("¿Atendido?", ["No", "Sí"], index=1, horizontal=True, key=K("atendido"))
    c10.checkbox("Atención registrada en Panacea", key=K("reg_panacea"))

    pr1, pr2 = st.columns([1, 1])
    pr1.checkbox("Paciente priorizado", key=K("pac_priorizado"))
    show_origen = st.session_state.get(K("pac_priorizado"), False)
    if show_origen:
        current = st.session_state.get(K("priorizado_origen")) or "(Seleccione)"
        pr2.selectbox("Origen priorización", options=["(Seleccione)"] + PRIORI_ORIGEN_OPTS, key=K("priorizado_origen"))
    else:
        st.session_state[K("priorizado_origen")] = "(Seleccione)"

    c11, c12 = st.columns([1, 1])
    c11.selectbox("Tipo de contacto", options=["(No especifica)"] + TIPOS_CONTACTO, key=K("tipo_contacto"))
    c12.number_input("Duración de la atención (minutos, opcional)", min_value=0, max_value=480, step=5, key=K("duracion_minutos"))

    observaciones = st.text_area("Observaciones", key=K("observaciones"))

    clicked = st.button("Guardar atención", type="primary", use_container_width=True, key=K("btn_guardar_atencion"))
    if clicked:
        faltantes = []
        if not pid:
            faltantes.append("Programa")
        if not cid:
            faltantes.append("Convenio")
        if not fid:
            faltantes.append("Profesional")
        if not institucion_id:
            faltantes.append("Institución")
        if not (st.session_state.get(K("pac_doc")) or "").strip():
            faltantes.append("Documento del paciente")
        if not (st.session_state.get(K("pac_nombre")) or "").strip():
            faltantes.append("Nombre del paciente")

        if st.session_state.get(K("pac_priorizado")) and st.session_state.get(K("priorizado_origen")) in (None, "", "(Seleccione)"):
            faltantes.append("Origen de priorización")

        if faltantes:
            error_toast("Faltan datos obligatorios: " + ", ".join(faltantes))
        else:
            try:
                dur = st.session_state.get(K("duracion_minutos")) or 0
                dur_val = int(dur) if dur and dur > 0 else None
                tc = st.session_state.get(K("tipo_contacto"))
                tipo_contacto_val = None if tc == "(No especifica)" else tc
                sexo_val = None if st.session_state[K("pac_sexo")] == "(No especifica)" else st.session_state[K("pac_sexo")]
                zona_val = None if st.session_state[K("pac_zona")] == "(No especifica)" else st.session_state[K("pac_zona")]

                pac_id = DATA.upsert_paciente(
                    numero_documento=(st.session_state[K("pac_doc")] or "").strip(),
                    nombre=(st.session_state[K("pac_nombre")] or "").strip(),
                    fecha_nacimiento=(st.session_state[K("pac_fecha_nac")] or None),
                    sexo=sexo_val,
                    telefono=(st.session_state[K("pac_telefono")] or None),
                    email=(st.session_state[K("pac_email")] or None),
                    direccion=(st.session_state[K("pac_direccion")] or None),
                    localidad=(st.session_state[K("pac_localidad")] or None),
                    municipio=(st.session_state[K("pac_municipio")] or None),
                    departamento=(st.session_state[K("pac_departamento")] or None),
                    zona=zona_val,
                )

                priorizado = bool(st.session_state[K("pac_priorizado")])
                priorizado_origen = (
                    None
                    if not priorizado or st.session_state[K("priorizado_origen")] in ("", "(Seleccione)")
                    else st.session_state[K("priorizado_origen")]
                )

                DATA.insert_registro(
                    fecha=st.session_state[K("fecha")],
                    programa_id=int(pid),
                    convenio_id=int(cid),
                    institucion_id=int(institucion_id),
                    Profesional_id=int(fid),
                    paciente_id=pac_id,
                    localidad=localidad_val,
                    municipio=municipio_val,
                    departamento=departamento_val,
                    numero_paciente=(st.session_state[K("pac_doc")] or "").strip(),
                    nombre_paciente=(st.session_state[K("pac_nombre")] or "").strip(),
                    actividad=st.session_state[K("actividad")],
                    atendido=True if st.session_state[K("atendido")] == "Sí" else False,
                    registrado_panacea=bool(st.session_state[K("reg_panacea")]),
                    paciente_creado_panacea=bool(st.session_state[K("pac_creado_panacea")]),
                    paciente_priorizado=priorizado,
                    priorizado_origen=priorizado_origen,
                    duracion_minutos=dur_val,
                    tipo_contacto=tipo_contacto_val,
                    observaciones=observaciones,
                    creado_por=auth_user,
                )
                success_toast("Atención registrada.")
                st.rerun()
            except Exception as e:
                error_toast(f"Error al guardar: {e}")

    st.markdown("---")
    with st.expander("📥 Carga masiva de atenciones (Excel/CSV)", expanded=False):
        def KM(x: str) -> str:
            return f"regm_{x}"

        tpl = plantilla_atenciones_df()

        def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as w:
                for name, df in sheets.items():
                    dd = df.copy()
                    dd.columns = [str(c)[:40] for c in dd.columns]
                    dd.to_excel(w, sheet_name=name[:31], index=False)
            return out.getvalue()

        tpl_xlsx = to_excel_bytes({"Atenciones": tpl})
        st.download_button(
            "Descargar plantilla (.xlsx)",
            data=tpl_xlsx,
            file_name="plantilla_atenciones.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=KM("dl_xlsx"),
        )
        st.download_button(
            "Descargar plantilla (.csv)",
            data=tpl.to_csv(index=False).encode("utf-8"),
            file_name="plantilla_atenciones.csv",
            mime="text/csv",
            use_container_width=True,
            key=KM("dl_csv"),
        )

        st.caption(
            "**Obligatorias**: fecha, programa, convenio, institucion, profesional, documento, nombre, actividad. "
            "**Opcionales**: departamento, municipio, localidad, atendido, registrado_panacea (atención), "
            "paciente_creado_panacea (paciente), **paciente_priorizado**, **priorizado_origen**, "
            "tipo_contacto, duracion_minutos, observaciones, sexo, fecha_nacimiento, "
            "telefono, email, direccion, zona."
        )

        up = st.file_uploader("Archivo de atenciones", type=["xlsx", "xls", "csv"], key=KM("file"))
        if up is not None and st.button("Procesar atenciones", type="primary", use_container_width=True, key=KM("btn")):
            try:
                df_up = read_table_upload(up)
                ok, errores = procesar_atenciones_masivo(df_up, auth_user or "desconocido")
                if ok:
                    success_toast(f"Atenciones procesadas: {ok}")
                if errores:
                    st.error("Se encontraron errores:")
                    for e in errores[:500]:
                        st.write(f"- {e}")
                if ok:
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando archivo: {e}")

# ---------------- UI: LISTADO ----------------
def ui_registros():
    st.subheader("Listado de atenciones")
    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("Sin registros.")
        return

    if "tasa_atencion" in df.columns:
        df["tasa_atencion_%"] = (df["tasa_atencion"] * 100).round(1)

    show = [
        "id",
        "fecha",
        "programa",
        "convenio",
        "institucion",
        "Profesional",
        "actividad",
        "numero_paciente",
        "nombre_paciente",
        "tipo_contacto",
        "duracion_minutos",
        "atendido",
        "paciente_creado_panacea",
        "registrado_panacea",
        "paciente_priorizado",
        "priorizado_origen",
        "pacientes_programados",
        "pacientes_atendidos",
        "no_asistieron",
        "tasa_atencion_%",
        "observaciones",
        "creado_por",
        "creado_en",
        "actualizado_en",
    ]
    st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)

    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 3])
    rid = c1.number_input("ID de atención", min_value=1, step=1, key="lst_reg_id_sel")
    if c2.button("Eliminar atención", use_container_width=True, key="lst_btn_eliminar_reg"):
        try:
            DATA.delete_registro(int(rid))
            success_toast("Eliminado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

# ---------------- UI: DASHBOARD ----------------
def ui_dashboard():
    st.subheader("Dashboard de gestión")
    df = DATA.list_registros(st.session_state.filters)
    if df.empty:
        st.info("Sin datos para graficar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"])
    
    total_prog = int(df.shape[0])
    total_att = int(df[df["atendido"] == 1].shape[0])
    total_no = total_prog - total_att
    tasa = (total_att / total_prog * 100) if total_prog else 0.0
    
    total_min = int(df.get("duracion_minutos", pd.Series()).fillna(0).sum()) if "duracion_minutos" in df.columns else 0
    n_con = int(df.get("duracion_minutos", pd.Series()).notna().sum()) if "duracion_minutos" in df.columns else 0
    prom = (total_min / n_con) if n_con else 0.0
    horas = total_min / 60 if total_min > 0 else 0.0
    prod_ph = (total_att / horas) if horas > 0 else 0.0
    
    total_pan = int(df[df.get("registrado_panacea", 0) == 1].shape[0]) if "registrado_panacea" in df.columns else 0
    total_pac_creados = int(df[df.get("paciente_creado_panacea", 0) == 1].shape[0]) if "paciente_creado_panacea" in df.columns else 0
    total_priorizados = int(df[df.get("paciente_priorizado", 0) == 1].shape[0]) if "paciente_priorizado" in df.columns else 0
    brecha = total_att - total_pan

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total registros", f"{total_prog:,}".replace(",", "."))
    k2.metric("Atendidos", f"{total_att:,}".replace(",", "."))
    k3.metric("No asistieron", f"{total_no:,}".replace(",", "."))
    k4.metric("Tasa atención", f"{tasa:.1f}%")

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Minutos totales", f"{total_min:,}".replace(",", "."))
    k6.metric("Duración prom (min)", f"{prom:.1f}")
    k7.metric("Atenciones/hora", f"{prod_ph:.2f}")
    k8.metric("Atención en Panacea / brecha", f"{total_pan} / {brecha}")

    k9, k10 = st.columns([1, 1])
    k9.metric("Pacientes creados Panacea", f"{total_pac_creados:,}".replace(",", "."))
    k10.metric("Pacientes priorizados", f"{total_priorizados:,}".replace(",", "."))

    tdf = df.copy()
    tdf["atendido_num"] = df["atendido"].apply(lambda x: 1 if x == 1 else 0)
    tdf_agg = tdf.groupby(pd.Grouper(key="fecha", freq="W")).agg({
        "id": "count",
        "atendido_num": "sum"
    }).reset_index()
    tdf_agg.columns = ["fecha", "pacientes_programados", "pacientes_atendidos"]
    
    st.plotly_chart(
        px.line(tdf_agg, x="fecha", y=["pacientes_programados", "pacientes_atendidos"], 
                markers=True, title="Tendencia semanal"),
        use_container_width=True,
    )

    rank = (
        df[df["atendido"] == 1]
        .groupby("Profesional", dropna=True)
        .size()
        .sort_values(ascending=False)
        .head(15)
        .reset_index(name="pacientes_atendidos")
    )
    fig2 = px.bar(rank, x="Profesional", y="pacientes_atendidos", title="Top profesionales (atendidos)")
    fig2.update_layout(xaxis_tickangle=-40)
    st.plotly_chart(fig2, use_container_width=True)

    if "registrado_panacea" in df.columns:
        pan = (
            df.groupby("Profesional", dropna=True)
            .agg(
                pacientes_atendidos=("atendido", lambda x: (x == 1).sum()),
                cargadas_panacea=("registrado_panacea", lambda x: (x == 1).sum()),
            )
            .reset_index()
        )
        pan["brecha"] = pan["pacientes_atendidos"] - pan["cargadas_panacea"]
        fig2b = px.bar(
            pan.sort_values("brecha", ascending=False).head(15),
            x="Profesional",
            y=["pacientes_atendidos", "cargadas_panacea"],
            barmode="group",
            title="Atenciones vs Panacea por profesional",
        )
        fig2b.update_layout(xaxis_tickangle=-40)
        st.plotly_chart(fig2b, use_container_width=True)

    if "paciente_priorizado" in df.columns:
        dist = (
            df[df["paciente_priorizado"] == 1]
            .assign(prior_origen=df["priorizado_origen"].fillna("(Sin origen)"))
            .groupby("prior_origen")
            .size()
            .reset_index(name="priorizado")
            .sort_values("priorizado", ascending=False)
        )
        if not dist.empty:
            figp = px.bar(dist, x="prior_origen", y="priorizado", title="Pacientes priorizados por origen")
            figp.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(figp, use_container_width=True)

    act_sum = df.groupby("actividad").agg({
        "id": "count",
        "atendido": lambda x: (x == 1).sum()
    }).reset_index()
    act_sum.columns = ["actividad", "pacientes_programados", "pacientes_atendidos"]
    
    st.plotly_chart(
        px.bar(
            act_sum,
            x="actividad",
            y=["pacientes_programados", "pacientes_atendidos"],
            barmode="group",
            title="Por actividad",
        ),
        use_container_width=True,
    )

# ---------------- UI: REPORTES ----------------
def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in sheets.items():
            dd = df.copy()
            dd.columns = [str(c)[:40] for c in dd.columns]
            dd.to_excel(w, sheet_name=name[:31], index=False)
    return out.getvalue()

def ui_reportes():
    st.subheader("Reportes y descargas")
    
    df = DATA.list_registros(st.session_state.filters)
    df_viaticos = DATA.list_viaticos(st.session_state.filters)
    df_agenda = DATA.list_agenda(st.session_state.filters)
    df_papeleria = DATA.list_papeleria(st.session_state.filters)
    
    if df.empty and df_viaticos.empty and df_agenda.empty and df_papeleria.empty:
        st.info("Sin registros para descargar en el período seleccionado.")
        return

    sheets = {}
    
    if not df.empty:
        agg_prof = (
            df.groupby("Profesional", dropna=True)
            .agg(
                registros_totales=("id", "count"),
                pacientes_atendidos=("atendido", lambda x: (x == 1).sum()),
                cargadas_panacea=("registrado_panacea", lambda x: (x == 1).sum()),
                pac_creados_panacea=("paciente_creado_panacea", lambda x: (x == 1).sum()),
                priorizados=("paciente_priorizado", lambda x: (x == 1).sum()),
                minutos=("duracion_minutos", "sum"),
            )
            .reset_index()
        )
        agg_prof["tasa_atencion_%"] = np.where(
            agg_prof["registros_totales"] > 0,
            (agg_prof["pacientes_atendidos"] / agg_prof["registros_totales"] * 100).round(1),
            0,
        )
        agg_prof["brecha_panacea"] = agg_prof["pacientes_atendidos"] - agg_prof["cargadas_panacea"]

        por_inst = df.groupby("institucion", dropna=True).agg({
            "id": "count",
            "atendido": lambda x: (x == 1).sum()
        }).reset_index()
        por_inst.columns = ["institucion", "pacientes_programados", "pacientes_atendidos"]
        
        por_geo = (
            df.groupby(["departamento", "municipio"], dropna=True).agg({
                "id": "count",
                "atendido": lambda x: (x == 1).sum()
            })
            .reset_index()
        )
        por_geo.columns = ["departamento", "municipio", "pacientes_programados", "pacientes_atendidos"]
        
        por_act = df.groupby("actividad").agg({
            "id": "count",
            "atendido": lambda x: (x == 1).sum()
        }).reset_index()
        por_act.columns = ["actividad", "pacientes_programados", "pacientes_atendidos"]
        
        por_prior_origen = (
            df[df.get("paciente_priorizado", 0) == 1]
            .assign(prior_origen=df["priorizado_origen"].fillna("(Sin origen)"))
            .groupby("prior_origen")
            .size()
            .reset_index(name="pacientes_priorizados")
        )

        sheets["Detalle_Atenciones"] = df
        sheets["Por_Profesional"] = agg_prof
        sheets["Por_Institucion"] = por_inst
        sheets["Por_Geo"] = por_geo
        sheets["Por_Actividad"] = por_act
        if not por_prior_origen.empty:
            sheets["Prior_por_Origen"] = por_prior_origen

    if not df_viaticos.empty:
        sheets["Viaticos"] = df_viaticos
        viaticos_resumen = df_viaticos.groupby("Profesional", dropna=True).agg({
            "valor": ["count", "sum"]
        }).reset_index()
        viaticos_resumen.columns = ["Profesional", "cantidad_viaticos", "total_valor"]
        sheets["Viaticos_Resumen"] = viaticos_resumen

    if not df_agenda.empty:
        sheets["Agenda"] = df_agenda

    if not df_papeleria.empty:
        sheets["Papeleria"] = df_papeleria
        papel_resumen = df_papeleria.groupby(["item", "estado"], dropna=True).agg({
            "cantidad": "sum"
        }).reset_index()
        sheets["Papeleria_Resumen"] = papel_resumen

    xls = to_excel_bytes(sheets)
    
    st.download_button(
        "📥 Descargar reporte completo Excel (.xlsx)",
        data=xls,
        file_name=f"reporte_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="rep_btn_descargar_xlsx",
    )
    
    col1, col2, col3 = st.columns(3)
    
    if not df.empty:
        col1.download_button(
            "Atenciones (.csv)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"atenciones_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="rep_csv_atenciones",
        )
    
    if not df_viaticos.empty:
        col2.download_button(
            "Viáticos (.csv)",
            data=df_viaticos.to_csv(index=False).encode("utf-8"),
            file_name=f"viaticos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="rep_csv_viaticos",
        )
    
    if not df_papeleria.empty:
        col3.download_button(
            "Papelería (.csv)",
            data=df_papeleria.to_csv(index=False).encode("utf-8"),
            file_name=f"papeleria_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="rep_csv_papeleria",
        )

    st.markdown("### Resumen de datos en el período")
    
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Atenciones", len(df))
    r2.metric("Viáticos", len(df_viaticos))
    r3.metric("Eventos agenda", len(df_agenda))
    r4.metric("Solicitudes papel.", len(df_papeleria))

# ---------------- UI: VIATICOS (MEJORADO) ----------------
def ui_viaticos(auth_user: Optional[str]):
    st.subheader("Registro de viáticos")
    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha", value=date.today(), key="via_fecha")

    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = c2.selectbox("Programa (opcional)", options=["(Sin programa)"] + list(prog_map.keys()), key="via_programa")
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = c1.selectbox("Convenio (opcional)", options=["(Sin convenio)"] + list(conv_map.keys()), key="via_convenio")
    cid = conv_map.get(csel)

    prof = DATA.list_Profesionales(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c2.selectbox("Profesional (opcional)", options=["(Sin profesional)"] + list(prof_map.keys()), key="via_profesional")
    fid = prof_map.get(fsel)

    inst = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in inst.iterrows()} if not inst.empty else {}
    isel = st.selectbox("Institución destino (opcional)", options=["(Sin institución)"] + list(inst_map.keys()), key="via_institucion")
    iid = inst_map.get(isel)

    c5, c6 = st.columns([1, 1])
    req = c5.radio("¿Requiere viáticos?", ["No", "Sí"], index=1, horizontal=True, key="via_req")
    origen = c6.text_input("Sitio de origen", key="via_origen")
    destino = st.text_input("Sitio de destino", key="via_destino")
    valor = st.number_input("Valor de viáticos", min_value=0.0, step=1000.0, key="via_valor")
    obs = st.text_area("Observaciones (opcional)", key="via_obs")

    if st.button("Guardar viático", type="primary", use_container_width=True, key="via_guardar"):
        try:
            DATA.insert_viatico(
                fecha=fecha,
                programa_id=pid,
                convenio_id=cid,
                institucion_id=iid,
                Profesional_id=fid,
                requiere_viatico=(req == "Sí"),
                origen=origen,
                destino=destino,
                valor=valor if valor > 0 else None,
                observaciones=obs,
                creado_por=auth_user,
            )
            success_toast("Viático registrado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo guardar: {e}")

    st.markdown("### Listado de viáticos")
    df = DATA.list_viaticos(st.session_state.filters)
    if df.empty:
        st.info("Sin viáticos.")
    else:
        df["requiere_viatico"] = df["requiere_viatico"].map({1: "Sí", 0: "No"})
        show = [
            "id",
            "fecha",
            "programa",
            "convenio",
            "institucion",
            "Profesional",
            "requiere_viatico",
            "origen",
            "destino",
            "valor",
            "observaciones",
            "creado_por",
            "creado_en",
        ]
        st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)
        st.metric("Total viáticos (filtro)", f"${df['valor'].fillna(0).sum():,.0f}".replace(",", "."))

    # EDICIÓN/ELIMINACIÓN
    st.markdown("---")
    st.markdown("#### Editar / eliminar viático")
    e1, e2, e3 = st.columns([1, 1, 1])
    vid_in = e1.number_input("ID de viático", min_value=1, step=1, key="via_edit_id")
    cargar = e2.button("Cargar", key="via_edit_cargar")
    eliminar = e3.button("Eliminar", key="via_edit_eliminar")

    if eliminar:
        try:
            DATA.delete_viatico(int(vid_in))
            success_toast("Viático eliminado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    if cargar:
        rec = DATA.get_viatico_by_id(int(vid_in))
        if not rec:
            warn_toast("No existe viático con ese ID.")
        else:
            st.markdown("##### Editar viático")
            ed1, ed2 = st.columns([1, 1])
            new_fecha = ed1.date_input("Fecha", value=pd.to_datetime(rec["fecha"]).date(), key="via_edit_fecha")
            new_req = ed2.radio("¿Requiere?", ["No", "Sí"], 
                              index=1 if rec["requiere_viatico"] == 1 else 0, 
                              horizontal=True, key="via_edit_req")
            
            ed3, ed4 = st.columns([1, 1])
            new_origen = ed3.text_input("Origen", value=rec["origen"] or "", key="via_edit_origen")
            new_destino = ed4.text_input("Destino", value=rec["destino"] or "", key="via_edit_destino")
            
            new_valor = st.number_input("Valor", min_value=0.0, step=1000.0, 
                                      value=float(rec["valor"] or 0), key="via_edit_valor")
            new_obs = st.text_area("Observaciones", value=rec["observaciones"] or "", key="via_edit_obs")

            if st.button("Guardar cambios", type="primary", key="via_edit_guardar"):
                try:
                    DATA.update_viatico(
                        int(vid_in),
                        {
                            "fecha": new_fecha.strftime("%Y-%m-%d"),
                            "requiere_viatico": 1 if new_req == "Sí" else 0,
                            "origen": new_origen.strip() or None,
                            "destino": new_destino.strip() or None,
                            "valor": float(new_valor) if new_valor > 0 else None,
                            "observaciones": new_obs.strip() or None,
                        },
                    )
                    success_toast("Viático actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")

# ---------------- UI: PLANIFICADOR (MEJORADO) ----------------
def ui_planificador(auth_user: Optional[str]):
    st.subheader("Planificador (agenda)")

    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha", value=date.today(), key="ag_fecha")
    hi = c1.time_input("Hora inicio", value=dtime(8, 0), key="ag_hora_ini")
    hf = c2.time_input("Hora fin", value=dtime(9, 0), key="ag_hora_fin")
    titulo = st.text_input("Título", key="ag_titulo")
    descripcion = st.text_area("Descripción / notas", key="ag_descripcion")

    c3, c4 = st.columns([1, 1])
    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = c3.selectbox("Programa (opcional)", options=["(Sin programa)"] + list(prog_map.keys()), key="ag_programa")
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = c4.selectbox("Convenio (opcional)", options=["(Sin convenio)"] + list(conv_map.keys()), key="ag_convenio")
    cid = conv_map.get(csel)

    c5, c6 = st.columns([1, 1])
    inst = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in inst.iterrows()} if not inst.empty else {}
    isel = c5.selectbox("Institución (opcional)", options=["(Sin institución)"] + list(inst_map.keys()), key="ag_institucion")
    iid = inst_map.get(isel)

    prof = DATA.list_Profesionales(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = c6.selectbox("Profesional (opcional)", options=["(Sin profesional)"] + list(prof_map.keys()), key="ag_Profesional")
    fid = prof_map.get(fsel)

    if st.button("Guardar evento", type="primary", use_container_width=True, key="ag_guardar"):
        if not titulo.strip():
            warn_toast("Título obligatorio.")
        else:
            try:
                DATA.insert_agenda_event(fecha, hi, hf, titulo, descripcion, pid, cid, iid, fid, auth_user)
                success_toast("Evento registrado.")
                st.rerun()
            except Exception as e:
                error_toast(f"No se pudo guardar: {e}")

    st.markdown("### Agenda (según filtros)")
    df = DATA.list_agenda(st.session_state.filters)
    if df.empty:
        st.info("Sin eventos.")
    else:
        show = [
            "id",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "titulo",
            "descripcion",
            "programa",
            "convenio",
            "institucion",
            "Profesional",
            "creado_por",
            "creado_en",
        ]
        st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)

    # EDITAR / ELIMINAR
    st.markdown("---")
    st.markdown("#### Editar / eliminar evento")
    c7, c8, c9 = st.columns([1, 1, 1])
    eid = c7.number_input("ID de evento", min_value=1, step=1, key="ag_edit_id")
    cargar = c8.button("Cargar", key="ag_edit_cargar")
    eliminar = c9.button("Eliminar", key="ag_edit_eliminar")

    if eliminar:
        try:
            DATA.delete_agenda_event(int(eid))
            success_toast("Evento eliminado.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    if cargar:
        ev = DATA.get_agenda_by_id(int(eid))
        if not ev:
            warn_toast("No existe evento con ese ID.")
        else:
            st.markdown("##### Editar evento")
            e1, e2 = st.columns([1, 1])
            new_fecha = e1.date_input("Fecha", value=pd.to_datetime(ev["fecha"]).date(), key="ag_edit_fecha")
            new_hi = e1.time_input(
                "Hora inicio", value=dtime.fromisoformat(ev["hora_inicio"]) if ev["hora_inicio"] else dtime(8, 0), key="ag_edit_hi"
            )
            new_hf = e2.time_input(
                "Hora fin", value=dtime.fromisoformat(ev["hora_fin"]) if ev["hora_fin"] else dtime(9, 0), key="ag_edit_hf"
            )
            new_tit = st.text_input("Título", value=ev["titulo"], key="ag_edit_titulo")
            new_desc = st.text_area("Descripción / notas", value=ev["descripcion"] or "", key="ag_edit_desc")

            if st.button("Guardar cambios", type="primary", key="ag_edit_guardar"):
                try:
                    DATA.update_agenda_event(
                        int(eid),
                        {
                            "fecha": new_fecha.strftime("%Y-%m-%d"),
                            "hora_inicio": new_hi.strftime("%H:%M") if new_hi else None,
                            "hora_fin": new_hf.strftime("%H:%M") if new_hf else None,
                            "titulo": new_tit.strip(),
                            "descripcion": new_desc.strip() or None,
                        },
                    )
                    success_toast("Evento actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")

# ---------------- UI: PAPELERIA (CORREGIDO) ----------------
def ui_papeleria(auth_user: Optional[str]):
    st.subheader("Solicitud de papelería")

    c1, c2 = st.columns([1, 1])
    fecha = c1.date_input("Fecha", value=date.today(), key="pp_fecha")
    item = c1.text_input("Ítem solicitado (ej. Historias, Carpetas, Esferos, Hojas A4)", key="pp_item")
    cantidad = c2.number_input("Cantidad", min_value=1, step=1, key="pp_cantidad")
    estado = c2.selectbox("Estado", options=["Solicitado", "Aprobado", "Entregado"], index=0, key="pp_estado")
    observ = st.text_area("Observaciones", key="pp_obs")

    progs = DATA.list_programas()
    prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
    psel = st.selectbox("Programa (opcional)", options=["(Sin programa)"] + list(prog_map.keys()), key="pp_prog")
    pid = prog_map.get(psel)

    conv = DATA.list_convenios(pid) if pid else DATA.list_convenios()
    conv_map = {r["nombre"]: int(r["id"]) for _, r in conv.iterrows()} if not conv.empty else {}
    csel = st.selectbox("Convenio (opcional)", options=["(Sin convenio)"] + list(conv_map.keys()), key="pp_conv")
    cid = conv_map.get(csel)

    inst = DATA.list_instituciones()
    inst_map = {r["nombre"]: int(r["id"]) for _, r in inst.iterrows()} if not inst.empty else {}
    isel = st.selectbox("Institución (opcional)", options=["(Sin institución)"] + list(inst_map.keys()), key="pp_inst")
    iid = inst_map.get(isel)

    prof = DATA.list_Profesionales(pid, cid)
    prof_map = {r["nombre"]: int(r["id"]) for _, r in prof.iterrows()} if not prof.empty else {}
    fsel = st.selectbox("Profesional (opcional)", options=["(Sin profesional)"] + list(prof_map.keys()), key="pp_prof")
    fid = prof_map.get(fsel)

    if st.button("Guardar solicitud", type="primary", use_container_width=True, key="pp_guardar"):
        if not item.strip():
            warn_toast("Debes indicar el ítem solicitado.")
        else:
            try:
                DATA.insert_papeleria(fecha, pid, cid, iid, fid, item, int(cantidad), estado, observ or None, auth_user)
                success_toast("Solicitud registrada.")
                st.rerun()
            except Exception as e:
                error_toast(f"No se pudo guardar: {e}")

    st.markdown("### Solicitudes registradas (según filtros)")
    df = DATA.list_papeleria(st.session_state.filters)
    if df.empty:
        st.info("Sin solicitudes.")
    else:
        show = [
            "id",
            "fecha",
            "item",
            "cantidad",
            "estado",
            "programa",
            "convenio",
            "institucion",
            "Profesional",
            "observaciones",
            "creado_por",
            "creado_en",
        ]
        st.dataframe(df[[c for c in show if c in df.columns]], use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Editar / eliminar solicitud")
    c7, c8, c9 = st.columns([1, 1, 1])
    pid_in = c7.number_input("ID de solicitud", min_value=1, step=1, key="pp_edit_id")
    cargar = c8.button("Cargar", key="pp_edit_cargar")
    eliminar = c9.button("Eliminar", key="pp_edit_eliminar")

    if eliminar:
        try:
            DATA.delete_papeleria(int(pid_in))
            success_toast("Solicitud eliminada.")
            st.rerun()
        except Exception as e:
            error_toast(f"No se pudo eliminar: {e}")

    if cargar:
        rec = DATA.get_papeleria_by_id(int(pid_in))
        if not rec:
            warn_toast("No existe solicitud con ese ID.")
        else:
            st.markdown("##### Editar solicitud")
            e1, e2 = st.columns([1, 1])
            new_fecha = e1.date_input("Fecha", value=pd.to_datetime(rec["fecha"]).date(), key="pp_edit_fecha")
            new_item = e1.text_input("Ítem", value=rec["item"], key="pp_edit_item")
            new_cant = e2.number_input("Cantidad", min_value=1, step=1, value=int(rec["cantidad"] or 1), key="pp_edit_cant")
            new_estado = e2.selectbox(
                "Estado",
                options=["Solicitado", "Aprobado", "Entregado"],
                index=["Solicitado", "Aprobado", "Entregado"].index(rec["estado"] or "Solicitado"),
                key="pp_edit_estado",
            )
            new_obs = st.text_area("Observaciones", value=rec["observaciones"] or "", key="pp_edit_obs")

            if st.button("Guardar cambios", type="primary", key="pp_edit_guardar"):
                try:
                    DATA.update_papeleria(
                        int(pid_in),
                        {
                            "fecha": new_fecha.strftime("%Y-%m-%d"),
                            "item": new_item.strip(),
                            "cantidad": int(new_cant),
                            "estado": new_estado,
                            "observaciones": new_obs.strip() or None,
                        },
                    )
                    success_toast("Solicitud actualizada.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo actualizar: {e}")

# ---------------- UI: CONFIGURACION (CON EDICIÓN EN PROGRAMAS Y CONVENIOS) ----------------
def ui_configuracion():
    st.subheader("Configuración de catálogos")
    tabs = st.tabs(["Programas", "Convenios", "Instituciones", "Profesionales", "Pacientes"])

    # ==================== PROGRAMAS ====================
    with tabs[0]:
        st.markdown("#### Agregar programa")
        c1, c2 = st.columns([2, 1])
        pnom = c1.text_input("Nombre del programa", key="cfg_prog_nombre")
        if c2.button("Agregar programa", use_container_width=True, key="cfg_btn_add_programa"):
            if not pnom.strip():
                warn_toast("Escribe un nombre.")
            else:
                DATA.upsert_programa(pnom.strip())
                success_toast("Programa agregado.")
                st.rerun()
        
        st.markdown("#### Programas existentes")
        df_prog = DATA.list_programas()
        st.dataframe(df_prog, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar programa")
        
        # Inicializar estado de edición
        if "editing_prog_id" not in st.session_state:
            st.session_state.editing_prog_id = None
        if "editing_prog_data" not in st.session_state:
            st.session_state.editing_prog_data = {}
        
        # Controles para cargar y eliminar
        p1, p2, p3 = st.columns([1, 1, 1])
        pid_edit = p1.number_input("ID programa", min_value=1, step=1, key="cfg_prog_edit_id")
        cargar_prog = p2.button("📋 Cargar", use_container_width=True, key="cfg_prog_cargar")
        eliminar_prog = p3.button("🗑️ Eliminar", use_container_width=True, key="cfg_prog_eliminar")
        
        # Eliminar
        if eliminar_prog:
            try:
                DATA.delete_programa(int(pid_edit))
                success_toast("Programa desactivado.")
                st.session_state.editing_prog_id = None
                st.session_state.editing_prog_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_prog:
            prog_rec = DATA.get_programa_by_id(int(pid_edit))
            if not prog_rec:
                warn_toast("No existe programa con ese ID.")
                st.session_state.editing_prog_id = None
                st.session_state.editing_prog_data = {}
            else:
                st.session_state.editing_prog_id = prog_rec["id"]
                st.session_state.editing_prog_data = {
                    "nombre": prog_rec["nombre"]
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_prog_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando programa ID: {st.session_state.editing_prog_id}**")
            
            with st.form(key="form_edit_prog", clear_on_submit=False):
                new_nom = st.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_prog_data["nombre"],
                    key="form_edit_prog_nom"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip():
                    error_toast("El nombre es obligatorio")
                else:
                    try:
                        DATA.update_programa(st.session_state.editing_prog_id, new_nom.strip())
                        success_toast("✅ Programa actualizado correctamente")
                        st.session_state.editing_prog_id = None
                        st.session_state.editing_prog_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_prog_id = None
                st.session_state.editing_prog_data = {}
                st.rerun()

    # ==================== CONVENIOS ====================
    with tabs[1]:
        st.markdown("#### Agregar convenio")
        progs = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}
        c1, c2, c3 = st.columns([2, 2, 1])
        cv_prog = c1.selectbox("Programa", options=list(prog_map.keys()) if prog_map else [], key="cfg_conv_prog")
        cv_nom = c2.text_input("Nombre del convenio", key="cfg_conv_nombre")
        if c3.button("Agregar convenio", use_container_width=True, key="cfg_btn_add_convenio"):
            if not (cv_prog and cv_nom.strip()):
                warn_toast("Selecciona programa y nombre.")
            else:
                DATA.upsert_convenio(cv_nom.strip(), prog_map[cv_prog])
                success_toast("Convenio agregado.")
                st.rerun()
        
        st.markdown("#### Convenios existentes")
        df_conv = DATA.list_convenios()
        st.dataframe(df_conv, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar convenio")
        
        # Inicializar estado de edición
        if "editing_conv_id" not in st.session_state:
            st.session_state.editing_conv_id = None
        if "editing_conv_data" not in st.session_state:
            st.session_state.editing_conv_data = {}
        
        # Controles para cargar y eliminar
        cv1, cv2, cv3 = st.columns([1, 1, 1])
        cid_edit = cv1.number_input("ID convenio", min_value=1, step=1, key="cfg_conv_edit_id")
        cargar_conv = cv2.button("📋 Cargar", use_container_width=True, key="cfg_conv_cargar")
        eliminar_conv = cv3.button("🗑️ Eliminar", use_container_width=True, key="cfg_conv_eliminar")
        
        # Eliminar
        if eliminar_conv:
            try:
                DATA.delete_convenio(int(cid_edit))
                success_toast("Convenio desactivado.")
                st.session_state.editing_conv_id = None
                st.session_state.editing_conv_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_conv:
            conv_rec = DATA.get_convenio_by_id(int(cid_edit))
            if not conv_rec:
                warn_toast("No existe convenio con ese ID.")
                st.session_state.editing_conv_id = None
                st.session_state.editing_conv_data = {}
            else:
                st.session_state.editing_conv_id = conv_rec["id"]
                st.session_state.editing_conv_data = {
                    "nombre": conv_rec["nombre"],
                    "programa_id": conv_rec["programa_id"]
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_conv_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando convenio ID: {st.session_state.editing_conv_id}**")
            
            with st.form(key="form_edit_conv", clear_on_submit=False):
                # Obtener lista de programas actualizada
                progs_edit = DATA.list_programas()
                prog_map_edit = {r["nombre"]: int(r["id"]) for _, r in progs_edit.iterrows()} if not progs_edit.empty else {}
                prog_reverse_map = {v: k for k, v in prog_map_edit.items()}
                
                current_prog_name = prog_reverse_map.get(st.session_state.editing_conv_data["programa_id"], "")
                
                cve1, cve2 = st.columns([1, 1])
                new_prog = cve1.selectbox(
                    "Programa *",
                    options=list(prog_map_edit.keys()),
                    index=list(prog_map_edit.keys()).index(current_prog_name) if current_prog_name in prog_map_edit.keys() else 0,
                    key="form_edit_conv_prog"
                )
                
                new_nom = cve2.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_conv_data["nombre"],
                    key="form_edit_conv_nom"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip() or not new_prog:
                    error_toast("El nombre y programa son obligatorios")
                else:
                    try:
                        DATA.update_convenio(
                            st.session_state.editing_conv_id, 
                            new_nom.strip(),
                            prog_map_edit[new_prog]
                        )
                        success_toast("✅ Convenio actualizado correctamente")
                        st.session_state.editing_conv_id = None
                        st.session_state.editing_conv_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_conv_id = None
                st.session_state.editing_conv_data = {}
                st.rerun()

    # ==================== INSTITUCIONES ====================
    with tabs[2]:
        st.markdown("#### Agregar institución")
        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.2, 1.2, 1])
        i_nom = c1.text_input("Nombre institución", key="cfg_inst_nombre")
        i_loc = c2.text_input("Localidad", key="cfg_inst_localidad")
        i_mun = c3.text_input("Municipio", key="cfg_inst_municipio")
        i_dep = c4.text_input("Departamento", key="cfg_inst_departamento")
        if c5.button("Agregar institución", use_container_width=True, key="cfg_btn_add_inst"):
            if not i_nom.strip():
                warn_toast("Escribe el nombre.")
            else:
                DATA.upsert_institucion(i_nom.strip(), i_loc or None, i_mun or None, i_dep or None)
                success_toast("Institución agregada.")
                st.rerun()
        
        st.markdown("#### Instituciones existentes")
        df_inst = DATA.list_instituciones()
        st.dataframe(df_inst, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar institución")
        
        # Inicializar estado de edición
        if "editing_inst_id" not in st.session_state:
            st.session_state.editing_inst_id = None
        if "editing_inst_data" not in st.session_state:
            st.session_state.editing_inst_data = {}
        
        # Controles para cargar y eliminar
        e1, e2, e3 = st.columns([1, 1, 1])
        iid_edit = e1.number_input("ID institución", min_value=1, step=1, key="cfg_inst_edit_id")
        cargar_inst = e2.button("📋 Cargar", use_container_width=True, key="cfg_inst_cargar")
        eliminar_inst = e3.button("🗑️ Eliminar", use_container_width=True, key="cfg_inst_eliminar")
        
        # Eliminar
        if eliminar_inst:
            try:
                DATA.delete_institucion(int(iid_edit))
                success_toast("Institución desactivada.")
                st.session_state.editing_inst_id = None
                st.session_state.editing_inst_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_inst:
            inst_rec = DATA.get_institucion_by_id(int(iid_edit))
            if not inst_rec:
                warn_toast("No existe institución con ese ID.")
                st.session_state.editing_inst_id = None
                st.session_state.editing_inst_data = {}
            else:
                st.session_state.editing_inst_id = inst_rec["id"]
                st.session_state.editing_inst_data = {
                    "nombre": inst_rec["nombre"],
                    "localidad": inst_rec["localidad"] or "",
                    "municipio": inst_rec["municipio"] or "",
                    "departamento": inst_rec["departamento"] or ""
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_inst_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando institución ID: {st.session_state.editing_inst_id}**")
            
            with st.form(key="form_edit_inst", clear_on_submit=False):
                ed1, ed2, ed3, ed4 = st.columns([2, 1, 1, 1])
                
                new_nom = ed1.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_inst_data["nombre"],
                    key="form_edit_inst_nom"
                )
                new_loc = ed2.text_input(
                    "Localidad", 
                    value=st.session_state.editing_inst_data["localidad"],
                    key="form_edit_inst_loc"
                )
                new_mun = ed3.text_input(
                    "Municipio", 
                    value=st.session_state.editing_inst_data["municipio"],
                    key="form_edit_inst_mun"
                )
                new_dep = ed4.text_input(
                    "Departamento", 
                    value=st.session_state.editing_inst_data["departamento"],
                    key="form_edit_inst_dep"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip():
                    error_toast("El nombre es obligatorio")
                else:
                    try:
                        DATA.update_institucion(
                            st.session_state.editing_inst_id, 
                            new_nom.strip(), 
                            new_loc.strip() or None, 
                            new_mun.strip() or None, 
                            new_dep.strip() or None
                        )
                        success_toast("✅ Institución actualizada correctamente")
                        st.session_state.editing_inst_id = None
                        st.session_state.editing_inst_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_inst_id = None
                st.session_state.editing_inst_data = {}
                st.rerun()

        st.markdown("---")
        st.markdown("### Carga masiva de instituciones")
        file_inst = st.file_uploader("Archivo de instituciones (Excel o CSV)", type=["xlsx", "xls", "csv"], key="cfg_up_instituciones")
        if file_inst is not None and st.button("Procesar instituciones", key="cfg_btn_proc_inst"):
            try:
                df_inst_up = read_table_upload(file_inst)
                if "nombre" not in df_inst_up.columns:
                    st.error(f"El archivo debe contener 'nombre'. Columnas: {list(df_inst_up.columns)}")
                else:
                    ok = 0
                    for _, r in df_inst_up.iterrows():
                        nom = str(r.get("nombre", "")).strip()
                        if not nom:
                            continue
                        DATA.upsert_institucion(
                            nom,
                            str(r.get("localidad", "")).strip() or None if "localidad" in df_inst_up.columns else None,
                            str(r.get("municipio", "")).strip() or None if "municipio" in df_inst_up.columns else None,
                            str(r.get("departamento", "")).strip() or None if "departamento" in df_inst_up.columns else None,
                        )
                        ok += 1
                    success_toast(f"Se procesaron {ok} instituciones.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando instituciones: {e}")

    # ==================== PROFESIONALES ====================
    with tabs[3]:
        st.markdown("#### Agregar profesional")
        progs = DATA.list_programas()
        prog_map = {r["nombre"]: int(r["id"]) for _, r in progs.iterrows()} if not progs.empty else {}

        # Necesitamos un programa y convenio fijos para profesionales
        # Por simplicidad, tomamos el primero disponible
        PROGRAMA_FIJO_ID = list(prog_map.values())[0] if prog_map else None
        conv_fijos = DATA.list_convenios(PROGRAMA_FIJO_ID) if PROGRAMA_FIJO_ID else pd.DataFrame()
        CONVENIO_FIJO_ID = int(conv_fijos.iloc[0]["id"]) if not conv_fijos.empty else None

        c1, c2, c3 = st.columns([2, 1.2, 1.4])
        f_nom = c1.text_input("Nombre profesional", key="cfg_prof_nombre")
        f_doc = c2.text_input("Documento (opcional)", key="cfg_prof_doc")
        f_email = c3.text_input("Email (opcional)", key="cfg_prof_email")
        
        zona_opts = ["(No especifica)", "Urbana", "Rural"]
        f_zona = st.selectbox("Zona (opcional)", options=zona_opts, key="cfg_prof_zona")

        if st.button("Agregar profesional", use_container_width=True, key="cfg_btn_add_prof"):
            if not f_nom.strip():
                warn_toast("Escribe el nombre.")
            else:
                zona = None if f_zona == "(No especifica)" else f_zona
                DATA.upsert_Profesional(f_nom.strip(), f_doc or None, f_email or None, PROGRAMA_FIJO_ID, CONVENIO_FIJO_ID, zona)
                success_toast("Profesional agregado.")
                st.rerun()

        st.markdown("#### Profesionales existentes")
        df_prof = DATA.list_Profesionales()
        st.dataframe(df_prof, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar profesional")
        
        # Inicializar estado de edición
        if "editing_prof_id" not in st.session_state:
            st.session_state.editing_prof_id = None
        if "editing_prof_data" not in st.session_state:
            st.session_state.editing_prof_data = {}
        
        # Controles para cargar y eliminar
        p1, p2, p3 = st.columns([1, 1, 1])
        fid_edit = p1.number_input("ID profesional", min_value=1, step=1, key="cfg_prof_edit_id")
        cargar_prof = p2.button("📋 Cargar", use_container_width=True, key="cfg_prof_cargar")
        eliminar_prof = p3.button("🗑️ Eliminar", use_container_width=True, key="cfg_prof_eliminar")
        
        # Eliminar
        if eliminar_prof:
            try:
                DATA.delete_profesional(int(fid_edit))
                success_toast("Profesional desactivado.")
                st.session_state.editing_prof_id = None
                st.session_state.editing_prof_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_prof:
            prof_rec = DATA.get_profesional_by_id(int(fid_edit))
            if not prof_rec:
                warn_toast("No existe profesional con ese ID.")
                st.session_state.editing_prof_id = None
                st.session_state.editing_prof_data = {}
            else:
                st.session_state.editing_prof_id = prof_rec["id"]
                st.session_state.editing_prof_data = {
                    "nombre": prof_rec["nombre"],
                    "documento": prof_rec["documento"] or "",
                    "email": prof_rec["email"] or "",
                    "zona": prof_rec["zona"] or "(No especifica)"
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_prof_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando profesional ID: {st.session_state.editing_prof_id}**")
            
            with st.form(key="form_edit_prof", clear_on_submit=False):
                pe1, pe2, pe3 = st.columns([2, 1, 1])
                
                new_nom = pe1.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_prof_data["nombre"],
                    key="form_edit_prof_nom"
                )
                new_doc = pe2.text_input(
                    "Documento", 
                    value=st.session_state.editing_prof_data["documento"],
                    key="form_edit_prof_doc"
                )
                new_email = pe3.text_input(
                    "Email", 
                    value=st.session_state.editing_prof_data["email"],
                    key="form_edit_prof_email"
                )
                
                zona_opts = ["(No especifica)", "Urbana", "Rural"]
                current_zona = st.session_state.editing_prof_data["zona"]
                if current_zona not in zona_opts:
                    current_zona = "(No especifica)"
                
                new_zona = st.selectbox(
                    "Zona",
                    options=zona_opts,
                    index=zona_opts.index(current_zona),
                    key="form_edit_prof_zona"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_nom.strip():
                    error_toast("El nombre es obligatorio")
                else:
                    try:
                        DATA.update_profesional(
                            st.session_state.editing_prof_id, 
                            new_nom.strip(), 
                            new_doc.strip() or None,
                            new_email.strip() or None,
                            PROGRAMA_FIJO_ID,
                            CONVENIO_FIJO_ID,
                            None if new_zona == "(No especifica)" else new_zona
                        )
                        success_toast("✅ Profesional actualizado correctamente")
                        st.session_state.editing_prof_id = None
                        st.session_state.editing_prof_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_prof_id = None
                st.session_state.editing_prof_data = {}
                st.rerun()

        st.markdown("---")
        st.markdown("### Carga masiva de profesionales")
        st.caption("Columnas: **nombre** (obligatoria), opcionales: documento, email, zona (Rural/Urbana).")
        file_prof = st.file_uploader("Archivo de profesionales", type=["xlsx", "xls", "csv"], key="cfg_up_profesionales")
        if file_prof is not None and st.button("Procesar profesionales", key="cfg_btn_proc_prof"):
            try:
                df_prof_up = read_table_upload(file_prof)
                if "nombre" not in df_prof_up.columns:
                    st.error(f"El archivo debe contener 'nombre'. Columnas: {list(df_prof_up.columns)}")
                else:
                    ok = 0
                    for _, r in df_prof_up.iterrows():
                        nom = str(r.get("nombre", "")).strip()
                        if not nom:
                            continue
                        doc = str(r.get("documento", "")).strip() if pd.notna(r.get("documento")) else None
                        email = str(r.get("email", "")).strip() if pd.notna(r.get("email")) else None
                        zona = str(r.get("zona", "")).strip() if pd.notna(r.get("zona")) else None
                        if zona not in ("Rural", "Urbana"):
                            zona = None
                        DATA.upsert_Profesional(nom, doc, email, PROGRAMA_FIJO_ID, CONVENIO_FIJO_ID, zona)
                        ok += 1
                    success_toast(f"Se procesaron {ok} profesionales.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando profesionales: {e}")

    # ==================== PACIENTES ====================
    with tabs[4]:
        st.markdown("### Gestión de pacientes")
        c1, c2 = st.columns([1.2, 2])
        cfg_doc = c1.text_input("Documento (cédula)", key="cfg_pac_doc")
        cfg_nom = c2.text_input("Nombre completo", key="cfg_pac_nombre")

        c3, c4, c5 = st.columns([1, 1, 1])
        cfg_nac = c3.text_input("Fecha de nacimiento (AAAA-MM-DD, opcional)", key="cfg_pac_fecha_nac")
        sexo_opts = ["(No especifica)", "F", "M", "Otro"]
        cfg_sexo = c4.selectbox("Sexo (opcional)", sexo_opts, key="cfg_pac_sexo")
        cfg_tel = c5.text_input("Teléfono (opcional)", key="cfg_pac_tel")

        c6, c7 = st.columns([1, 1])
        cfg_email = c6.text_input("Email (opcional)", key="cfg_pac_email")
        cfg_dir = c7.text_input("Dirección (opcional)", key="cfg_pac_dir")

        c8, c9, c10 = st.columns([1, 1, 1])
        cfg_loc = c8.text_input("Localidad (opcional)", key="cfg_pac_loc")
        cfg_mun = c9.text_input("Municipio (opcional)", key="cfg_pac_mun")
        cfg_dep = c10.text_input("Departamento (opcional)", key="cfg_pac_dep")

        zc1, _ = st.columns([1, 3])
        zona_opts = ["(No especifica)", "Urbana", "Rural"]
        cfg_zona = zc1.selectbox("Zona (opcional)", zona_opts, key="cfg_pac_zona")

        if st.button("Guardar / actualizar paciente", key="cfg_btn_guardar_paciente"):
            if not cfg_doc.strip() or not cfg_nom.strip():
                warn_toast("Documento y nombre son obligatorios.")
            else:
                try:
                    DATA.upsert_paciente(
                        cfg_doc.strip(),
                        cfg_nom.strip(),
                        cfg_nac or None,
                        None if cfg_sexo == "(No especifica)" else cfg_sexo,
                        cfg_tel or None,
                        cfg_email or None,
                        cfg_dir or None,
                        cfg_loc or None,
                        cfg_mun or None,
                        cfg_dep or None,
                        None if cfg_zona == "(No especifica)" else cfg_zona,
                    )
                    success_toast("Paciente guardado/actualizado.")
                    st.rerun()
                except Exception as e:
                    error_toast(f"No se pudo guardar: {e}")

        st.markdown("#### Pacientes existentes")
        df_pac = DATA.list_pacientes()
        st.dataframe(df_pac, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### ✏️ Editar / Eliminar paciente")
        
        # Inicializar estado de edición
        if "editing_pac_id" not in st.session_state:
            st.session_state.editing_pac_id = None
        if "editing_pac_data" not in st.session_state:
            st.session_state.editing_pac_data = {}
        
        # Controles para cargar y eliminar
        pa1, pa2, pa3 = st.columns([1, 1, 1])
        pac_id_edit = pa1.number_input("ID paciente", min_value=1, step=1, key="cfg_pac_edit_id")
        cargar_pac = pa2.button("📋 Cargar", use_container_width=True, key="cfg_pac_cargar")
        eliminar_pac = pa3.button("🗑️ Eliminar", use_container_width=True, key="cfg_pac_eliminar")
        
        # Eliminar
        if eliminar_pac:
            try:
                DATA.delete_paciente(int(pac_id_edit))
                success_toast("Paciente desactivado.")
                st.session_state.editing_pac_id = None
                st.session_state.editing_pac_data = {}
                st.rerun()
            except Exception as e:
                error_toast(f"Error: {e}")
        
        # Cargar datos para edición
        if cargar_pac:
            pac_rec = DATA.get_paciente_by_id(int(pac_id_edit))
            if not pac_rec:
                warn_toast("No existe paciente con ese ID.")
                st.session_state.editing_pac_id = None
                st.session_state.editing_pac_data = {}
            else:
                st.session_state.editing_pac_id = pac_rec["id"]
                st.session_state.editing_pac_data = {
                    "numero_documento": pac_rec["numero_documento"],
                    "nombre": pac_rec["nombre"],
                    "fecha_nacimiento": pac_rec["fecha_nacimiento"] or "",
                    "sexo": pac_rec["sexo"] if pac_rec["sexo"] in ["F", "M", "Otro"] else "(No especifica)",
                    "telefono": pac_rec["telefono"] or "",
                    "email": pac_rec["email"] or "",
                    "direccion": pac_rec["direccion"] or "",
                    "localidad": pac_rec["localidad"] or "",
                    "municipio": pac_rec["municipio"] or "",
                    "departamento": pac_rec["departamento"] or "",
                    "zona": pac_rec["zona"] if pac_rec["zona"] in ["Urbana", "Rural"] else "(No especifica)"
                }
                st.rerun()
        
        # Mostrar formulario de edición
        if st.session_state.editing_pac_id is not None:
            st.markdown("---")
            st.success(f"📝 **Editando paciente ID: {st.session_state.editing_pac_id}**")
            
            with st.form(key="form_edit_pac", clear_on_submit=False):
                pae1, pae2 = st.columns([1, 2])
                new_doc = pae1.text_input(
                    "Documento *", 
                    value=st.session_state.editing_pac_data["numero_documento"],
                    key="form_edit_pac_doc"
                )
                new_nom = pae2.text_input(
                    "Nombre *", 
                    value=st.session_state.editing_pac_data["nombre"],
                    key="form_edit_pac_nom"
                )
                
                pae3, pae4, pae5 = st.columns([1, 1, 1])
                new_fnac = pae3.text_input(
                    "Fecha nacimiento", 
                    value=st.session_state.editing_pac_data["fecha_nacimiento"],
                    key="form_edit_pac_fnac"
                )
                
                sexo_opts = ["(No especifica)", "F", "M", "Otro"]
                current_sexo = st.session_state.editing_pac_data["sexo"]
                new_sexo = pae4.selectbox(
                    "Sexo",
                    options=sexo_opts,
                    index=sexo_opts.index(current_sexo),
                    key="form_edit_pac_sexo"
                )
                
                new_tel = pae5.text_input(
                    "Teléfono", 
                    value=st.session_state.editing_pac_data["telefono"],
                    key="form_edit_pac_tel"
                )
                
                pae6, pae7 = st.columns([1, 1])
                new_email = pae6.text_input(
                    "Email", 
                    value=st.session_state.editing_pac_data["email"],
                    key="form_edit_pac_email"
                )
                new_dir = pae7.text_input(
                    "Dirección", 
                    value=st.session_state.editing_pac_data["direccion"],
                    key="form_edit_pac_dir"
                )
                
                pae8, pae9, pae10 = st.columns([1, 1, 1])
                new_loc = pae8.text_input(
                    "Localidad", 
                    value=st.session_state.editing_pac_data["localidad"],
                    key="form_edit_pac_loc"
                )
                new_mun = pae9.text_input(
                    "Municipio", 
                    value=st.session_state.editing_pac_data["municipio"],
                    key="form_edit_pac_mun"
                )
                new_dep = pae10.text_input(
                    "Departamento", 
                    value=st.session_state.editing_pac_data["departamento"],
                    key="form_edit_pac_dep"
                )
                
                zona_opts = ["(No especifica)", "Urbana", "Rural"]
                current_zona = st.session_state.editing_pac_data["zona"]
                new_zona = st.selectbox(
                    "Zona",
                    options=zona_opts,
                    index=zona_opts.index(current_zona),
                    key="form_edit_pac_zona"
                )
                
                col_save, col_cancel = st.columns([1, 1])
                submit = col_save.form_submit_button("💾 Actualizar", type="primary", use_container_width=True)
                cancel = col_cancel.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if submit:
                if not new_doc.strip() or not new_nom.strip():
                    error_toast("Documento y nombre son obligatorios")
                else:
                    try:
                        DATA.upsert_paciente(
                            numero_documento=new_doc.strip(),
                            nombre=new_nom.strip(),
                            fecha_nacimiento=new_fnac.strip() or None,
                            sexo=None if new_sexo == "(No especifica)" else new_sexo,
                            telefono=new_tel.strip() or None,
                            email=new_email.strip() or None,
                            direccion=new_dir.strip() or None,
                            localidad=new_loc.strip() or None,
                            municipio=new_mun.strip() or None,
                            departamento=new_dep.strip() or None,
                            zona=None if new_zona == "(No especifica)" else new_zona
                        )
                        success_toast("✅ Paciente actualizado correctamente")
                        st.session_state.editing_pac_id = None
                        st.session_state.editing_pac_data = {}
                        st.rerun()
                    except Exception as e:
                        error_toast(f"Error al actualizar: {e}")
            
            if cancel:
                st.session_state.editing_pac_id = None
                st.session_state.editing_pac_data = {}
                st.rerun()

        st.markdown("---")
        st.markdown("### Carga masiva de pacientes")
        st.caption(
            "Obligatorias: **documento**, **nombre**. Opcionales: fecha_nacimiento, sexo, telefono, email, "
            "direccion, localidad, municipio, departamento, zona (Rural/Urbana)."
        )
        file_pac = st.file_uploader("Archivo de pacientes (Excel o CSV)", type=["xlsx", "xls", "csv"], key="cfg_up_pacientes")
        if file_pac is not None and st.button("Procesar pacientes", key="cfg_btn_proc_pac"):
            try:
                df_pac_up = read_table_upload(file_pac)
                if not {"documento", "nombre"}.issubset(df_pac_up.columns):
                    st.error(f"El archivo debe contener 'documento' y 'nombre'. Columnas: {list(df_pac_up.columns)}")
                else:
                    ok = 0
                    for _, r in df_pac_up.iterrows():
                        doc = str(r.get("documento", "")).strip()
                        nom = str(r.get("nombre", "")).strip()
                        if not doc or not nom:
                            continue
                        zona = (
                            str(r.get("zona", "")).strip()
                            if "zona" in df_pac_up.columns and pd.notna(r.get("zona"))
                            else None
                        )
                        if zona not in ("Rural", "Urbana"):
                            zona = None
                        DATA.upsert_paciente(
                            numero_documento=doc,
                            nombre=nom,
                            fecha_nacimiento=str(r.get("fecha_nacimiento"))
                            if "fecha_nacimiento" in df_pac_up.columns and pd.notna(r.get("fecha_nacimiento"))
                            else None,
                            sexo=str(r.get("sexo")).strip() if "sexo" in df_pac_up.columns and pd.notna(r.get("sexo")) else None,
                            telefono=str(r.get("telefono")).strip()
                            if "telefono" in df_pac_up.columns and pd.notna(r.get("telefono"))
                            else None,
                            email=str(r.get("email")).strip() if "email" in df_pac_up.columns and pd.notna(r.get("email")) else None,
                            direccion=str(r.get("direccion")).strip()
                            if "direccion" in df_pac_up.columns and pd.notna(r.get("direccion"))
                            else None,
                            localidad=str(r.get("localidad")).strip()
                            if "localidad" in df_pac_up.columns and pd.notna(r.get("localidad"))
                            else None,
                            municipio=str(r.get("municipio")).strip()
                            if "municipio" in df_pac_up.columns and pd.notna(r.get("municipio"))
                            else None,
                            departamento=str(r.get("departamento")).strip()
                            if "departamento" in df_pac_up.columns and pd.notna(r.get("departamento"))
                            else None,
                            zona=zona,
                        )
                        ok += 1
                    success_toast(f"Se procesaron {ok} pacientes.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error procesando pacientes: {e}")

# ---------------- UI: RESPALDO (MEJORADO CON RESTAURACIÓN) ----------------
def ui_respaldo():
    st.subheader("Respaldo de la base de datos")
    st.caption("Descarga la base SQLite actual y/o un ZIP con CSV y schema.sql.")

    col1, col2 = st.columns(2)
    if os.path.exists(DB_SQLITE_PATH):
        col1.download_button(
            "⬇️ Descargar base (.db)",
            data=backup_sqlite_file(),
            file_name=f"respaldo_sqlite_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
            mime="application/octet-stream",
            use_container_width=True,
            key="bk_btn_db",
        )
    else:
        col1.warning("No se encontró el archivo de base de datos actual.")

    col2.download_button(
        "⬇️ Descargar ZIP (.db + CSV + schema)",
        data=build_zip_backup(),
        file_name=f"respaldo_productividad_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
        mime="application/zip",
        use_container_width=True,
        key="bk_btn_zip",
    )

    st.markdown("---")
    st.markdown("### 📤 Restaurar desde respaldo")
    
    uploaded_db = st.file_uploader(
        "Cargar archivo .db de respaldo", 
        type=["db"], 
        key="restore_db_file"
    )
    
    if uploaded_db is not None:
        st.warning("⚠️ Esto sobrescribirá la base de datos actual")
        
        if st.button("Restaurar base de datos", type="primary", key="restore_btn"):
            try:
                global SQLITE_CONN, DATA
                
                # Cerrar conexión
                try:
                    SQLITE_CONN.close()
                except:
                    pass
                
                # Guardar respaldo actual por si acaso
                if os.path.exists(DB_SQLITE_PATH):
                    backup_name = f"{DB_SQLITE_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.copy2(DB_SQLITE_PATH, backup_name)
                    st.info(f"Respaldo automático creado: {backup_name}")
                
                # Escribir archivo subido
                with open(DB_SQLITE_PATH, "wb") as f:
                    f.write(uploaded_db.getvalue())
                
                # Reconectar
                SQLITE_CONN = get_db_connection()
                DATA = DataAccess(SQLITE_CONN)
                
                # Verificar
                count = SQLITE_CONN.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
                success_toast(f"✅ Base restaurada correctamente. {count} registros encontrados.")
                st.rerun()
                
            except Exception as e:
                error_toast(f"Error restaurando: {e}")
                st.code(traceback.format_exc())

    st.markdown("---")
    with st.expander("⚠️ Reiniciar base (acción destructiva)", expanded=False):
        st.warning("Esto borrará información. Haz un respaldo antes.")
        metodo = st.radio(
            "Método de reinicio",
            ["Vaciar tablas (conservar archivo .db)", "Borrar archivo .db (recrear esquema en blanco)"],
            index=0,
            horizontal=False,
            key="reset_metodo",
        )
        confirma = st.text_input("Escribe exactamente: BORRAR TODO", key="reset_confirm")
        colA, colB = st.columns([1, 3])
        ejecutar = colA.button("Reiniciar ahora", type="primary", use_container_width=True, key="reset_go")

        if ejecutar:
            if confirma.strip() != "BORRAR TODO":
                st.error("Confirma escribiendo 'BORRAR TODO' exactamente.")
            else:
                m = "vaciar" if metodo.startswith("Vaciar") else "borrar_archivo"
                ok = _reset_database(m)
                if ok:
                    st.success("Base reiniciada correctamente. Recarga la página.")
                    st.rerun()

def _reset_database(method: str):
    global SQLITE_CONN, DATA
    try:
        if method == "vaciar":
            # Cerrar conexión actual
            try:
                SQLITE_CONN.close()
            except:
                pass
            
            # Reconectar y vaciar
            SQLITE_CONN = sqlite3.connect(DB_SQLITE_PATH, check_same_thread=False)
            SQLITE_CONN.execute("PRAGMA foreign_keys=OFF;")
            
            tablas = ["registros", "viaticos", "agenda", "papeleria",
                     "Profesionales", "pacientes", "instituciones", "convenios", "programas"]
            
            for t in tablas:
                try:
                    SQLITE_CONN.execute(f"DELETE FROM {t};")
                    st.write(f"✓ Tabla {t} vaciada")
                except Exception as e:
                    st.warning(f"⚠ Error en {t}: {e}")
            
            try:
                SQLITE_CONN.execute("DELETE FROM sqlite_sequence;")
            except:
                pass
            
            SQLITE_CONN.execute("PRAGMA foreign_keys=ON;")
            SQLITE_CONN.commit()
            
            # Recrear esquema
            ensure_sqlite_schema()
            
        elif method == "borrar_archivo":
            try:
                SQLITE_CONN.close()
            except:
                pass
            
            if os.path.exists(DB_SQLITE_PATH):
                os.remove(DB_SQLITE_PATH)
                st.write(f"✓ Archivo {DB_SQLITE_PATH} eliminado")
            
            # Esperar un momento
            time.sleep(0.5)
        
        # Reconectar
        SQLITE_CONN = get_db_connection()
        ensure_sqlite_schema()
        DATA = DataAccess(SQLITE_CONN)
        
        return True
        
    except Exception as e:
        st.error(f"Error al reiniciar: {e}")
        st.code(traceback.format_exc())
        return False

# ---------------- MAIN ----------------
def main():
    st.markdown(f"# {APP_ICON} {APP_TITLE}")
    st.caption("Base SQLite local (`productividad_Profesionales.db`). Usuarios del mismo enlace comparten la misma información.")
    
    # DIAGNÓSTICO
    if st.sidebar.checkbox("🔍 Mostrar diagnóstico", value=False):
        st.sidebar.markdown("### Diagnóstico de BD")
        db_exists = os.path.exists(DB_SQLITE_PATH)
        st.sidebar.write(f"Archivo existe: {db_exists}")
        if db_exists:
            db_size = os.path.getsize(DB_SQLITE_PATH)
            st.sidebar.write(f"Tamaño: {db_size:,} bytes")
            try:
                count = SQLITE_CONN.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
                st.sidebar.write(f"Registros en BD: {count}")
            except Exception as e:
                st.sidebar.error(f"Error leyendo BD: {e}")
    
    sidebar_filters()
    render_login()

    if not st.session_state.user:
        st.info("Inicia sesión para usar el aplicativo.")
        return

    user = st.session_state.user
    role = st.session_state.role

    tabs_admin = [
        "Registrar atenciones",
        "Listado",
        "Dashboard",
        "Reportes",
        "Viáticos",
        "Planificador",
        "Papelería",
        "Configuración",
        "Respaldo",
    ]
    tabs_pro = ["Registrar atenciones", "Listado", "Viáticos", "Planificador", "Papelería"]
    tabs = st.tabs(tabs_admin if role == "admin" else tabs_pro)

    if role == "admin":
        with tabs[0]:
            ui_cargar_datos(user)
        with tabs[1]:
            ui_registros()
        with tabs[2]:
            ui_dashboard()
        with tabs[3]:
            ui_reportes()
        with tabs[4]:
            ui_viaticos(user)
        with tabs[5]:
            ui_planificador(user)
        with tabs[6]:
            ui_papeleria(user)
        with tabs[7]:
            ui_configuracion()
        with tabs[8]:
            ui_respaldo()
    else:
        with tabs[0]:
            ui_cargar_datos(user)
        with tabs[1]:
            ui_registros()
        with tabs[2]:
            ui_viaticos(user)
        with tabs[3]:
            ui_planificador(user)
        with tabs[4]:
            ui_papeleria(user)

if __name__ == "__main__":
    main()




